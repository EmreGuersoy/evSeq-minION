# Import third party packages
import re

# Write a dictionary for reverse complements
ReverseCompDict = {"A": "T",
                     "T": "A",
                     "C": "G",
                     "G": "C",
                     "N": "N"}

# Define the allowed bases
AllowedBases = {"A", "T", "C", "G", "N"}
AllowedBasesNoDeg = {"A", "T", "C", "G"}

# Define the allowed wells
AllowedWells = {'A01', 'A02', 'A03', 'A04', 'A05', 'A06', 'A07', 'A08', 'A09', 
                 'A10', 'A11', 'A12', 'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 
                 'B07', 'B08', 'B09', 'B10', 'B11', 'B12', 'C01', 'C02', 'C03', 
                 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10', 'C11', 'C12', 
                 'D01', 'D02', 'D03', 'D04', 'D05', 'D06', 'D07', 'D08', 'D09', 
                 'D10', 'D11', 'D12', 'E01', 'E02', 'E03', 'E04', 'E05', 'E06', 
                 'E07', 'E08', 'E09', 'E10', 'E11', 'E12', 'F01', 'F02', 'F03', 
                 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10', 'F11', 'F12', 
                 'G01', 'G02', 'G03', 'G04', 'G05', 'G06', 'G07', 'G08', 'G09', 
                 'G10', 'G11', 'G12', 'H01', 'H02', 'H03', 'H04', 'H05', 'H06', 
                 'H07', 'H08', 'H09', 'H10', 'H11', 'H12'}

# Define a codon table
CodonTable = {'TTT': 'F', 'TTC': 'F', 'TTA': 'L', 'TTG': 'L', 'TCT': 'S', 
               'TCC': 'S', 'TCA': 'S', 'TCG': 'S', 'TAT': 'Y', 'TAC': 'Y', 
               'TGT': 'C', 'TGC': 'C', 'TGG': 'W', 'CTT': 'L', 'CTC': 'L', 
               'CTA': 'L', 'CTG': 'L', 'CCT': 'P', 'CCC': 'P', 'CCA': 'P', 
               'CCG': 'P', 'CAT': 'H', 'CAC': 'H', 'CAA': 'Q', 'CAG': 'Q', 
               'CGT': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R', 'ATT': 'I', 
               'ATC': 'I', 'ATA': 'I', 'ATG': 'M', 'ACT': 'T', 'ACC': 'T', 
               'ACA': 'T', 'ACG': 'T', 'AAT': 'N', 'AAC': 'N', 'AAA': 'K', 
               'AAG': 'K', 'AGT': 'S', 'AGC': 'S', 'AGA': 'R', 'AGG': 'R', 
               'GTT': 'V', 'GTC': 'V', 'GTA': 'V', 'GTG': 'V', 'GCT': 'A', 
               'GCC': 'A', 'GCA': 'A', 'GCG': 'A', 'GAT': 'D', 'GAC': 'D', 
               'GAA': 'E', 'GAG': 'E', 'GGT': 'G', 'GGC': 'G', 'GGA': 'G', 
               'GGG': 'G', 'TAG': '*', 'TAA': '*', 'TGA': '*'}

# Define a dictionary which links basepairs to indices and the reverse.
BpToInd = {"A": 0, 
            "T": 1,
            "C": 2,
            "G": 3,
            "N": 4,
            "-": 5}
IndToBp = {v: k for k, v in BpToInd.items()}
BpOpts = [IndToBp[ind] for ind in range(len(IndToBp))]

# Define a dictionary which links amino acids to indices and the reverse
AaToInd = {'A': 0, 'R': 1, 'N': 2, 'D': 3, 'C': 4, 'E': 5, 'Q': 6, 'G': 7, 
             'H': 8, 'I': 9, 'L': 10, 'K': 11, 'M': 12, 'F': 13, 'P': 14, 
             'S': 15, 'T': 16, 'W': 17, 'Y': 18, 'V': 19, '*': 20, '?': 21}
IndToAa = {v: k for k, v in AaToInd.items()}
AaOpts = [IndToAa[ind] for ind in range(len(IndToAa))]

# Construt a regular expression for parsing id lines of fastq files
IdParser = re.compile("(.+):(.+):(.+):(.+):(.+):(.+):(.+) ([0-9]):([A-Za-z]):([0-9]):(.+)")

# Define barcode length
BarcodeLength = 7

# Define the adapter lengths
AdapterLengthF = 27
AdapterLengthR = 26