# Import deSeq dependencies
from .Globals import (BP_TO_IND, AA_TO_IND, CODON_TABLE, AA_TO_IND, BP_ARRAY,
                      AA_ARRAY)

# Import other required modules
import os
import numpy as np
import pandas as pd
from Bio import SeqIO, pairwise2

class Well():
    
    # Initialization assigns attributes, reference sequences, and sequence pairs
    def __init__(self, seqpairs, refseq_df_info, save_dir):
        
        # Assign the sequence pairs as an attribute, unpack the refseq info, and store
        # the expected variable basepair positions as attirbutes
        self._all_seqpairs = seqpairs
        self._expected_variable_bp_positions = refseq_df_info["ExpectedVariablePositions"]
        self._index_plate = refseq_df_info["IndexPlate"]
        self._plate_nickname = refseq_df_info["PlateName"]
        self._well = refseq_df_info["Well"]
        self._reference_sequence = refseq_df_info["ReferenceSequence"]
        self._ref_len = len(self.reference_sequence)
        self._in_frame_ind = refseq_df_info["InFrameBase"] - 1 #Input is 1-indexed, so subtract 1
        self._bp_ind_start = refseq_df_info["BpIndStart"]
        self._aa_ind_start = refseq_df_info["AAIndStart"]
        
        # Generate save locations for alignment files
        self._fasta_loc = os.path.join(save_dir, "ParsedFilteredFastqs")
        self._alignment_loc = os.path.join(save_dir, "Alignments", 
                                       f"{self.index_plate}-{self.well}.txt")
        
        # Get the number of aas in the reference sequence
        self._n_aas = (self.ref_len - self.in_frame_ind) // 3
        
        # Calculate the expected count frequencies for both basepairs and
        # amino acids assuming no sequencing errors and no changes to reference sequence
        self.calculate_expected_arrays()
        
        # Calculate the variable amino acid positions
        self.calculate_expected_variable_aa_positions()
        
        # Create placeholders for a number of attributes. This is done to allow 
        # failing gracefully out of the analyze count functions
        # if we don't have any reads in a well
        self._unit_bp_freqs_no_gaps = None
        self._bp_position_counts = None
        self._all_variable_bp_positions = None
        self._variable_bp_type = None
        
        self._unit_aa_freqs_no_gaps = None
        self._aa_position_counts = None
        self._all_variable_aa_positions = None
        self._variable_aa_type = None
        
        self._all_bp_counts = None
        self._all_aa_counts = None
        
    # Write a function to calculate the expected reference amino acid and base sequences
    def calculate_expected_arrays(self):
    
        # Create arrays for storing expected results. 
        self._expected_bps = np.zeros([6, self.ref_len], dtype = int)
        self._expected_aas = np.zeros([23, self.n_aas], dtype = int)
                
        # Loop over the reference sequence and record expected basepairs
        for bp_ind, bp in enumerate(self.reference_sequence):
            self._expected_bps[BP_TO_IND[bp], bp_ind] += 1

        # Caculate last readable bp for translation
        last_readable_bp = self.in_frame_ind + self.n_aas * 3
        
        # Loop over the codons in the reference sequence and record
        aa_counter = 0
        for chunker in range(self.in_frame_ind, last_readable_bp, 3):

            # Identify the codon and translate
            codon = self.reference_sequence[chunker: chunker + 3]
            expected_aa = "?" if codon not in CODON_TABLE else CODON_TABLE[codon]

            # Record and increment counter
            self._expected_aas[AA_TO_IND[expected_aa], aa_counter] += 1
            aa_counter += 1
            
        # Make sure we are not double counting and that we are counting everything
        bp_test = np.sum(self.expected_bps, axis = 0)
        aa_test = np.sum(self.expected_aas, axis = 0)
        assert np.all(bp_test == 1), "Expected bp calculation is wrong"
        assert np.all(aa_test == 1), "Expected aa calculation is wrong"
        
        # Calculate and store the amino acid reference sequence
        aa_ref_inds = np.argwhere(np.transpose(self.expected_aas == 1))[:, 1]
        self._reference_sequence_aa = "".join(AA_ARRAY[aa_ref_inds].tolist())
        
    # Write a function for calculating the expected variable amino acid positions
    def calculate_expected_variable_aa_positions(self):

        # Get the number of expected variable basepair positions
        n_bp_positions = len(self.expected_variable_bp_positions)
        
        # If there are none, we have an empty array
        if n_bp_positions == 0:
            self._expected_variable_aa_positions = np.array([], dtype = int)
            
        # Otherwise, calculate the positions
        else:

            # Assert that the positions are sorted, unique, and divisible by 3
            assert sorted(self.expected_variable_bp_positions) == \
                self.expected_variable_bp_positions.tolist(), "Error in basepair sorting"
            assert len(set(self.expected_variable_bp_positions)) == n_bp_positions, "Duplicate basepairs found"
            assert n_bp_positions % 3 == 0, "Bp positions not divisible by 3"

            # Loop over the variable bp positions in chunks of 3. 
            self._expected_variable_aa_positions = np.full(int(n_bp_positions / 3), np.nan,
                                                          dtype = int)
            position_counter = 0
            for chunker in range(0, n_bp_positions, 3):

                # Grab the codon
                codon = self.expected_variable_bp_positions[chunker: chunker+3]

                # Assert that the codon positions are 1 apart
                assert (codon[1] - codon[0]) == 1, "Codon positions not in order"
                assert (codon[2] - codon[0]) == 2, "Codon positions not in order"

                # Calculate the amino acid position 
                self._expected_variable_aa_positions[position_counter] = int((codon[0] - self.in_frame_ind) / 3)
                position_counter += 1
                    
    # Write a function that makes pairwise and runs qc on pairwise alignments and then identifies usable
    # and paired alignments
    def align(self):
        
        # Run alignment on all seqpairs
        for seqpair in self.all_seqpairs:
            seqpair.align(self.reference_sequence)
            seqpair.qc_alignments()
        
        # Identify seqpairs that have at least one read passing alignment QC
        self._non_dud_alignments = tuple(filter(lambda x: not x.is_dud_post_alignment_qc(), self.all_seqpairs))
                
    # Write a function that analyzes alignments to generate count matrices
    def analyze_alignments(self, qual_thresh, variable_count):

        # Get the number of duds. If there we have less alignments that our 
        # variable threhold, return False
        n_non_duds = len(self.non_dud_alignments)
        if n_non_duds < variable_count:
            self._usable_reads = False
            return False
        
        # Create matrices in which to store counts
        self._all_bp_counts = np.zeros([n_non_duds, 6, self.ref_len], dtype = int)
        self._all_aa_counts = np.zeros([n_non_duds, 23, self.n_aas], dtype = int)
        
        # Loop over all non-dud seqpairs and record counts for each aa and sequence
        for pair_ind, seqpair in enumerate(self.non_dud_alignments):
            (self._all_bp_counts[pair_ind],
             self._all_aa_counts[pair_ind]) = seqpair.analyze_alignment(self.in_frame_ind, self.ref_len,
                                                                        self.n_aas, qual_thresh) 
            
        # Return true to signifify that we identified at least one non-dud.
        self._usable_reads = True
        return True
                
    # Write a function that calculates counts and frequencies by unit (e.g. amino acid or 
    # base pair) and position in the sequence. 
    @staticmethod
    def build_unit_counts_generic(count_array):
        
        # Get the counts for each unit (e.g. an amino acid or base pair) at each
        # position. For both the aa and bp count matrices, the last row is the gap character.
        # The gap character is ignored when generating counts
        by_unit_counts = count_array[:, :-1].sum(axis=0)
    
        # Now get the total counts at each position
        by_position_counts = by_unit_counts.sum(axis=0)

        # Convert counts for each unit at each position to frequency for
        # each unit at each position. Return 0 if the by_position counts
        # are also 0 (avoid divide by 0 error)
        by_unit_frequency = np.divide(by_unit_counts, by_position_counts,
                                     out = np.zeros_like(by_unit_counts, dtype = float),
                                     where = by_position_counts != 0)
        
        # If not keeping gaps, return the by position counts as well as the
        # unit counts and frequencies. Otherwise, just return the unit counts
        # and frequencies
        return by_unit_counts, by_unit_frequency, by_position_counts
        
    def build_unit_count_matrices(self):
        
        # Run the generic count calculator for aas and bps, ignoring gaps
        (self._unit_bp_counts_no_gaps, 
         self._unit_bp_freqs_no_gaps,
         self._bp_position_counts) = Well.build_unit_counts_generic(self.all_bp_counts)
        (self._unit_aa_counts_no_gaps,
         self._unit_aa_freqs_no_gaps,
         self._aa_position_counts) = Well.build_unit_counts_generic(self.all_aa_counts)
    
    # Now write a generic function for identifying variable positions
    @staticmethod
    def identify_variable_positions_generic(by_unit_frequency, expected_array, 
                                            variable_thresh, expected_variable_positions):
        
        # Compare the unit frequency to the expected array.
        # The furthest difference is 2 (e.g. if there are no reads matching to the
        # expected sequence), so take the absolute value is taken and the full
        # array divided by 2 to scale to a "percent different"
        difference_from_expectation_absolute = np.abs(by_unit_frequency - expected_array)
        average_difference_from_expectation = np.sum(difference_from_expectation_absolute, axis = 0)/2
        
        # Get the length of the unit frequency first axis
        n_units = by_unit_frequency.shape[0]

        # Compare the unit frequency to the expected array.
        # The furthest difference is 2 (e.g. if there are no reads matching to the
        # expected sequence), so take the absolute value is taken and the full
        # array divided by 2 to scale to a "percent different"
        difference_from_expectation_absolute = np.abs(by_unit_frequency - expected_array[:n_units])
        average_difference_from_expectation = np.sum(difference_from_expectation_absolute, axis = 0)/2

        # Find positions that have differences greater than the threshold
        identified_variable_positions = np.argwhere(average_difference_from_expectation > 
                                                    variable_thresh).flatten()
        identified_variable_positions.sort()
        
        # Get the unique set of variable positions
        expected_set = set(expected_variable_positions)
        all_found = np.unique(np.concatenate((expected_variable_positions, 
                                              identified_variable_positions)))
        all_found.sort()
        
        # Determine if the variation is expected or not. Return this along with all_found
        expected_variation = np.array(["" if var in expected_set else "Unexpected Variation"
                                       for var in all_found])
        
        return all_found, expected_variation
        
    # Write a function for identifying variable positions in both the amino acid
    # and basepair counts
    def identify_variable_positions(self, variable_thresh):
        
        # Find the variable basepair and amino acid positions. Note that gaps are not used 
        # when finding variable positions
        (self._all_variable_bp_positions, 
         self._variable_bp_type) = Well.identify_variable_positions_generic(self.unit_bp_freqs_no_gaps,
                                                                            self.expected_bps[:-1],
                                                                            variable_thresh,
                                                                           self.expected_variable_bp_positions)
        (self._all_variable_aa_positions,
         self._variable_aa_type) = Well.identify_variable_positions_generic(self.unit_aa_freqs_no_gaps,
                                                                            self.expected_aas[:-1],
                                                                            variable_thresh,
                                                                           self.expected_variable_aa_positions)
    
    # Write a function that analyzes and reports unpaired counts
    def analyze_unpaired_counts_generic(self, unit_freq_array, total_count_array, 
                                        all_variable_positions, expectation_array,
                                        unit_array, unit_type, variable_thresh,
                                        pos_offset):
        
        # Define output columns
        unit_pos = f"{unit_type}Position" # Create a name for the unit position
        columns = ("IndexPlate", "Plate", "Well",  unit_pos, unit_type,
                   "AlignmentFrequency", "WellSeqDepth", "Flag")
        
        # Define a dataframe to use for dead wells
        dead_df = pd.DataFrame([[self.index_plate, self.plate_nickname,
                                 self.well, "#DEAD#", "#DEAD#", 0,
                                 len(self.non_dud_alignments), "#DEAD#"]],
                               columns = columns)
        
        # If there are no reads, return that this is a dead well
        if not self.usable_reads:
            return dead_df, dead_df
        
        # If there are no variable positions, return wild type with the average
        # number of counts
        if len(all_variable_positions) == 0:
            
            # Get the mean read depth over all positions.
            average_counts_by_position = int(np.mean(total_count_array))
            
            # Create an output dataframe and return
            output_df = pd.DataFrame([[self.index_plate, self.plate_nickname, self.well, 
                                       "#PARENT#", "#PARENT#", 1 - variable_thresh,
                                       average_counts_by_position, "#PARENT#"]],
                                     columns = columns)
            return output_df, output_df
                
        # Get the variable frequencies
        variable_freqs = np.transpose(unit_freq_array[:, all_variable_positions])
        total_counts = total_count_array[all_variable_positions]

        # Identify non-zero positions
        nonzero_inds = np.argwhere(variable_freqs != 0)
        
        # If there are no non-zero positions with our desired reads, this well is
        # dead. 
        if nonzero_inds.shape[0] == 0:
            return dead_df, dead_df
    
        # Pull the variable amino acid positons, their frequencies/counts, and 
        # the associated amino acids. Also update positions for output: the offset
        # is added to match the desired indexing of the user
        variable_positions = (all_variable_positions[nonzero_inds[:, 0]]) + pos_offset
        variable_expectation = expectation_array[nonzero_inds[:, 0]]
        variable_total_counts = total_counts[nonzero_inds[:, 0]]
        variable_units = unit_array[nonzero_inds[:, 1]]
        nonzero_freqs = variable_freqs[nonzero_inds[:, 0], nonzero_inds[:, 1]]
        
        # We cannot have more counts than seqpairs
        assert variable_total_counts.max() <= len(self.non_dud_alignments), "Counting error"
        
        # Format for output and convert to a dataframe
        output_formatted = [[self.index_plate, self.plate_nickname, self.well, 
                           position, unit, freq, depth, flag] for 
                           position, unit, freq, depth, flag in 
                           zip(variable_positions, variable_units, nonzero_freqs,
                              variable_total_counts, variable_expectation)]
        output_df = pd.DataFrame(output_formatted, columns = columns)
        
        # Get the max output
        freq_and_pos = output_df.loc[:, [unit_pos, "AlignmentFrequency"]]
        max_inds = freq_and_pos.groupby(unit_pos).idxmax().AlignmentFrequency.values
        max_by_position = output_df.loc[max_inds]
        
        return output_df, max_by_position
    
    # Write a function that generates the unpaired analysis outputs for 
    # both basepairs and amino acids
    def analyze_unpaired_counts(self, variable_thresh):
        
        # Get the output format for basepairs
        (self._unpaired_bp_output,
         self._unpaired_bp_output_max) = self.analyze_unpaired_counts_generic(self.unit_bp_freqs_no_gaps,
                                                                              self.bp_position_counts,
                                                                              self.all_variable_bp_positions,
                                                                              self.variable_bp_type,
                                                                              BP_ARRAY, "Bp", variable_thresh,
                                                                              self.bp_ind_start)
        
        # Get the output format for amino acids
        (self._unpaired_aa_output,
         self._unpaired_aa_output_max) = self.analyze_unpaired_counts_generic(self.unit_aa_freqs_no_gaps,
                                                                              self.aa_position_counts,
                                                                              self.all_variable_aa_positions,
                                                                              self.variable_aa_type,
                                                                              AA_ARRAY, "Aa", variable_thresh,
                                                                              self.aa_ind_start)
    
    
    # Write a function that analyzes and reports paired counts
    def analyze_paired_counts_generic(self, variable_positions, all_counts, unit_array,
                                      reference_sequence, variable_thresh, variable_count,
                                      pos_offset):
        
        # Define output columns
        columns = ("IndexPlate", "Plate", "Well", "VariantCombo", "SimpleCombo",
                   "VariantsFound", "AlignmentFrequency", "WellSeqDepth",
                   "VariantSequence")
        
        # If there are no usable reads, return a dead dataframe
        if not self.usable_reads:
            return pd.DataFrame([[self.index_plate, self.plate_nickname, self.well,
                                  "#DEAD#", "#DEAD#", 0, 0, 0, "#DEAD#"]], columns = columns)
        
        # Get the number of positions
        n_positions = len(variable_positions)            

        # Get the counts of alignments that are paired end
        paired_alignment_inds = np.array([i for i, seqpair in enumerate(self.non_dud_alignments)
                                          if seqpair.is_paired_post_alignment_qc()])
        
        # If there are no paired reads, return a dead dataframe
        n_paired = len(paired_alignment_inds)
        if n_paired < variable_count:
            
            # Create a dataframe and return
            return pd.DataFrame([[self.index_plate, self.plate_nickname, self.well,
                                  "#DEAD#", "#DEAD#", 0, 0, n_paired, "#DEAD#"]],
                                columns = columns)
        
        # Get the counts for the paired alignment seqpairs
        paired_alignment_counts = all_counts[paired_alignment_inds]
        
        # Get the mean read depth over all positions.
        average_counts_by_position = int(np.mean(paired_alignment_counts.sum(axis = (0, 1))))
        
        # If there are no variable positions, return wild type with the average number of counts
        if n_positions == 0:
            
            # Create a dataframe and return
            return pd.DataFrame([[self.index_plate, self.plate_nickname, self.well,
                                  "#PARENT#", "#PARENT#", 0, 1 - variable_thresh,
                                  average_counts_by_position, reference_sequence]],
                                columns = columns)

        # Get the positions with variety
        variable_position_counts = paired_alignment_counts[:, :, variable_positions]

        # Make sure all passed QC. This means that the sum over the last two indices
        # is equal to the number of amino acids. This works because amino acids are only
        # counted if they pass QC: for all to pass QC they must all have an index at some
        # position
        passing_qc = variable_position_counts[variable_position_counts.sum(axis = (1, 2)) == n_positions]
        
        # If too few pass QC, return a dead dataframe
        n_passing = len(passing_qc)
        if  n_passing < variable_count:
            
            # Create a dataframe and return
            return pd.DataFrame([[self.index_plate, self.plate_nickname, self.well,
                                  "#DEAD#", "#DEAD#", 0, 0,
                                  n_passing, "#DEAD#"]],
                                columns = columns)

        # Get the unique sequences that all passed QC
        unique_binary_combos, unique_counts = np.unique(passing_qc, axis = 0, return_counts = True)

        # We cannot have more counts than paired seqpairs
        assert unique_counts.max() <= len(paired_alignment_inds), "Counting error"
        
        # Get a frequency array
        seq_depth = unique_counts.sum()
        unique_freqs = unique_counts / seq_depth

        # Loop over the unique combos and format for output
        output = [None] * len(unique_counts)
        for unique_counter, unique_binary_combo in enumerate(unique_binary_combos):

            # Get the index profile. This maps each position to a unit position
            # in either `BP_ARRAY` or `AA_ARRAY`
            index_profile = np.argwhere(np.transpose(unique_binary_combo == 1))

            # Get the position and amino acid.
            unique_position_array = variable_positions[index_profile[:, 0]]
            unique_combo = unit_array[index_profile[:, 1]]

            # Make sure the output is sorted
            assert np.all(np.diff(unique_position_array)), "Output not sorted"

            # Construct a sequence based on the reference
            # Construct a combo name based on the combo and position
            new_seq = list(reference_sequence)
            combo_name = [None] * n_positions
            simple_combo = combo_name.copy()
            for combo_ind, (pos, unit) in enumerate(zip(unique_position_array, unique_combo)):

                # Update the sequence
                new_seq[pos] = unit

                # Update the combo name. Add the offset to the position index to get
                # the start id of the reference seqeunce
                combo_name[combo_ind] = f"{reference_sequence[pos]}{pos + pos_offset}{unit}"
                
                # Update the simple combo name
                simple_combo[combo_ind] = unit

            # Convert the new seq and new combo into strings
            new_seq = "".join(new_seq)
            combo_name = "_".join(combo_name)
            simple_combo = "".join(simple_combo)

            # Record output
            output[unique_counter] = [self.index_plate, self.plate_nickname, self.well,
                                     combo_name, simple_combo, n_positions,
                                     unique_freqs[unique_counter], seq_depth, new_seq]

        # Convert output to a dataframe
        return pd.DataFrame(output, columns = columns)
                                      
    # Analyze the paired data for both amino acids and basepairs                              
    def analyze_paired_counts(self, variable_thresh, variable_count):
        
        # Analyze the paired data for both amino acids and basepairs
        self._paired_bp_output = self.analyze_paired_counts_generic(self.all_variable_bp_positions,
                                                                    self.all_bp_counts, BP_ARRAY,
                                                                    self.reference_sequence,
                                                                    variable_thresh, variable_count,
                                                                    self.bp_ind_start)
        
        self._paired_aa_output = self.analyze_paired_counts_generic(self.all_variable_aa_positions,
                                                                    self.all_aa_counts, AA_ARRAY,
                                                                    self.reference_sequence_aa,
                                                                    variable_thresh, variable_count,
                                                                    self.aa_ind_start)
        
    # Write a function that outputs adapterless fastq files for all paired end seqpairs
    # Note that the reverse complement of 
    def write_fastqs(self):
        
        # Identify the paired end sequence pairs
        paired_end_alignments = tuple(filter(lambda x: x.is_paired(), self.all_seqpairs))
        
        # Build a list of sequences to save
        f_records_to_save = [seqpair.f_adapterless for seqpair in paired_end_alignments]
        r_records_to_save = [seqpair.sliced_r for seqpair in paired_end_alignments]
        assert len(f_records_to_save) == len(r_records_to_save), "Mismatch in number of paired ends"
            
        # Save the records
        with open(os.path.join(self.fasta_loc, "F", f"{self.index_plate}-{self.well}_R1.fastq"), "w") as f:
            SeqIO.write(f_records_to_save, f, "fastq")
        with open(os.path.join(self.fasta_loc, "R", f"{self.index_plate}-{self.well}_R2.fastq"), "w") as f:
            SeqIO.write(r_records_to_save, f, "fastq")
            
    # Write a function that returns all pairwise alignments formatted for saving
    def format_alignments(self):
        
        # Write a function that formats all alignments in a well
        formatted_alignments = [""] * int(len(self.all_seqpairs) * 5)
        alignment_counter = 0
        for pair_ind, seqpair in enumerate(self.all_seqpairs):

            # Add a header row
            formatted_alignments[alignment_counter] = f"\nAlignment {pair_ind}:"
            alignment_counter += 1

            # If we are using the forward alignment, add to the list
            if seqpair.use_f:
                formatted_alignments[alignment_counter] = "Forward:"
                alignment_counter += 1
                formatted_alignments[alignment_counter] = pairwise2.format_alignment(*seqpair.f_alignment)
                alignment_counter += 1

            # If we are using the reverse alignment, add to the list
            if seqpair.use_r:
                formatted_alignments[alignment_counter] = "Reverse:"
                alignment_counter += 1
                formatted_alignments[alignment_counter] = pairwise2.format_alignment(*seqpair.r_alignment)
                alignment_counter += 1

        # Join as one string and return with plate and well information
        return (self.alignment_loc, "\n".join(formatted_alignments[:alignment_counter]))
        
        
    # Define properties
    @property
    def all_seqpairs(self):
        return self._all_seqpairs
        
    @property
    def expected_variable_bp_positions(self):
        return self._expected_variable_bp_positions
    
    @property
    def expected_variable_aa_positions(self):
        return self._expected_variable_aa_positions
    
    @property
    def index_plate(self):
        return self._index_plate
    
    @property
    def plate_nickname(self):
        return self._plate_nickname
    
    @property
    def well(self):
        return self._well
    
    @property
    def reference_sequence(self):
        return self._reference_sequence
    
    @property
    def reference_sequence_aa(self):
        return self._reference_sequence_aa
    
    @property
    def ref_len(self):
        return self._ref_len
    
    @property
    def n_aas(self):
        return self._n_aas
    
    @property
    def in_frame_ind(self):
        return self._in_frame_ind
    
    @property
    def bp_ind_start(self):
        return self._bp_ind_start
    
    @property
    def aa_ind_start(self):
        return self._aa_ind_start
    
    @property
    def fasta_loc(self):
        return self._fasta_loc
    
    @property
    def alignment_loc(self):
        return self._alignment_loc
    
    @property
    def expected_bps(self):
        return self._expected_bps
    
    @property
    def expected_aas(self):
        return self._expected_aas
        
    @property
    def non_dud_alignments(self):
        return self._non_dud_alignments
    
    @property
    def usable_reads(self):
        return self._usable_reads
    
    @property
    def all_bp_counts(self):
        return self._all_bp_counts
    
    @property
    def all_aa_counts(self):
        return self._all_aa_counts
    
    @property
    def unit_bp_counts_no_gaps(self):
        return self._unit_bp_counts_no_gaps
    
    @property
    def unit_bp_freqs_no_gaps(self):
        return self._unit_bp_freqs_no_gaps
    
    @property
    def unit_aa_counts_no_gaps(self):
        return self._unit_aa_counts_no_gaps
    
    @property
    def unit_aa_freqs_no_gaps(self):
        return self._unit_aa_freqs_no_gaps
        
    @property
    def bp_position_counts(self):
        return self._bp_position_counts
    
    @property
    def aa_position_counts(self):
        return self._aa_position_counts
    
    @property
    def all_variable_bp_positions(self):
        return self._all_variable_bp_positions
    
    @property
    def all_variable_aa_positions(self):
        return self._all_variable_aa_positions
    
    @property
    def variable_bp_type(self):
        return self._variable_bp_type
    
    @property
    def variable_aa_type(self):
        return self._variable_aa_type
    
    @property
    def unpaired_bp_output(self):
        return self._unpaired_bp_output
    
    @property
    def unpaired_bp_output_max(self):
        return self._unpaired_bp_output_max
    
    @property
    def unpaired_aa_output(self):
        return self._unpaired_aa_output
    
    @property
    def unpaired_aa_output_max(self):
        return self._unpaired_aa_output_max
    
    @property
    def paired_bp_output(self):
        return self._paired_bp_output
    
    @property
    def paired_aa_output(self):
        return self._paired_aa_output