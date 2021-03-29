############################ imports ###########################################
import os
import os.path
import sys
from Bio import SeqIO
from Bio.Phylo.TreeConstruction import DistanceCalculator
from Bio import AlignIO
import argparse
import yaml
########################### functions ##########################################
def load_config(config_file):
    with open(config_file, 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

def merge(blast_results, insert_length):
    number_regions = 0
    for key in blast_results:
        locations = blast_results[key]
        locations = sorted(locations, key = lambda x: int(x[3]))
        #print("test")
        #print(locations)
        size_list = len(locations)

        j = 0

        while j < size_list-1:
            i = 1
            while i < size_list-1:

                if ((locations[j][0] < locations[i][0]) and (locations[j][1] > locations[i][0]) and (locations[j][5] == locations[i][5])):
                    #merge overlapping regions
                    locations[j][1] = max(locations[j][1], locations[i][1])
                    locations[j][2] = min(locations[j][2], locations[i][2])
                    locations.pop(i)
                    size_list -= 1
                    i -= 1
                elif ((locations[j][0] < locations[i][0]) and (locations[i][0] - locations[j][1] <= 2* insert_length) and (locations[j][5] == locations[i][5])):
                    #print(j)
                    locations[j][1] = max(locations[j][1], locations[i][1])
                    locations[j][2] = min(locations[j][2], locations[i][2])
                    locations.pop(i)
                    size_list -= 1
                    i -=1
                i += 1
            j += 1

        number_regions += len(locations)
        blast_results[key] = locations

    #print(blast_results)
    return blast_results, number_regions

def parse_blast(line, blast_results):
    # format blast line:  <contig> <sstart> <send> <evalue> <qstart> <qend> <strand>
    #fomrat dictionary: {node_name: [(<start>,<end>)]}
    #print(line)
    line = line.replace("\n", "")
    line_info = line.split("\t")
    #print(line_info)
    evalue = float(line_info[3])

    #cut off
    if evalue > 0.00001:
        return blast_results, evalue
    #add region to dictionary
    else:
        node_name, sstart, send, qstart, qend = line_info[0], line_info[1], line_info[2], line_info[4], line_info[5]
        split = node_name.split("|")

        # finding out on which strand tBLASTn founded a hit
        if sstart < send:
            strand = "+"
        else:
            sstart = line_info[2]
            send = line_info[1]
            strand = "-"

        #creating a dictionary that inlcudes every tBLASTn that is better as the evalue cut-off of 0.00001
        if len(split) > 1:
            node_name = split[1]
        if node_name in blast_results:
            list = blast_results[node_name]
            list.append([int(sstart),int(send), evalue, int(qstart), int(qend), strand])
            blast_results[node_name] = list
        else:
            blast_results[node_name] = [[int(sstart),int(send), evalue, int(qstart), int(qend), strand]]

    return blast_results, evalue

def candidate_regions(intron_length, evalue, tmp_path):
    ###################### extracting candidate regions ########################
    # info about output blast http://www.metagenomics.wiki/tools/blast/blastn-output-format-6
    blast_file = open(tmp_path + "/blast_results.out", "r")
    evalue = 0
    blast_results = {}
    #parsing blast output
    while True:
        line = blast_file.readline()
        #end of file is reached
        if not line:
            break
        #parsing blast output
        blast_results, evalue = parse_blast(line, blast_results)
        #evalue cut-off
        if not evalue <= evalue:
            break
    if blast_results == {}:
        return 0,0
    else:
        candidate_regions, number_regions = merge(blast_results, intron_length)
        #candidate_regions, number_regions = merge_regions(blast_results, cut_off)
        #print(candidate_regions, number_regions)
        return candidate_regions, number_regions

def extract_seq(region_dic, path, tmp_path):
    #print(region_dic)
    for key in region_dic:
        #print("blastdbcmd -db " + path + " -dbtype 'nucl' -entry " + key + " -out tmp/" + key + ".fasta -outfmt %f")
        os.system("blastdbcmd -db " + path + " -dbtype 'nucl' -entry " + key + " -out " + tmp_path + key + ".fasta -outfmt %f")

def augustus_ppx(regions, candidatesOutFile, length_extension, profile_path, augustus_ref_species, ass_name, group, tmp_path):
    output = open(candidatesOutFile, "w")

    for key in regions:
        locations = regions[key]
        counter = 0
        for i in locations:
            counter += 1
            start = str(i[0] - length_extension)
            end = str(i[1] + length_extension)
            name = key + "_" + str(counter)
            #print("augustus --proteinprofile=" + profile_path + " --predictionStart=" + start + " --predictionEnd=" + end + " --species=" + augustus_ref_species + " tmp/" + key + ".fasta > tmp/" + key + ".gff")
            os.system("augustus --protein=1 --proteinprofile=" + profile_path + " --predictionStart=" + start + " --predictionEnd=" + end + " --species=" + augustus_ref_species + " " + tmp_path + key + ".fasta > " + tmp_path + name + ".gff")
            os.system("getAnnoFasta.pl --seqfile=" + tmp_path + key + ".fasta " + tmp_path + name + ".gff")

            sequence_file = open(tmp_path + name + ".aa", "r")
            lines = sequence_file.readlines()
            for line in lines:
                if line[0] == ">":
                    id = line.replace(">", "")
                    header = ">" + group + "|" + ass_name + "|" + name + "_" + id
                    output.write(header)
                else:
                    output.write(line)
            sequence_file.close()

    output.close()

def searching_for_db(assembly_path):
    #print("test: " + str(assembly_path) + "\n")
    db_endings = ['.ndb', '.nhr', '.nin', '.nog', '.nos', '.not', '.nsq', '.ntf', '.nto']
    check = True
    for end in db_endings:
        #print(assembly_path + end + "\n")
        check = check and os.path.exists(assembly_path + end)
        #print(check)
    return check

def get_distance_biopython(file, matrix):
    aln = AlignIO.read(open(file), 'fasta')
    calculator = DistanceCalculator(matrix)
    dm = calculator.get_distance(aln)
    return dm

def readFasta(candidatesOutFile):
    seq_records = SeqIO.parse(candidatesOutFile, "fasta")
    return seq_records

def getSeedInfo(path):
    dic = {}
    seq_records = readFasta(path)
    for entry in seq_records:
        species = entry.id.split("|")[1]
        geneID = entry.id.split("|")[2]

        try:
            dic[species].append(geneID)
        except KeyError:
            dic[species] = [geneID]

    del seq_records
    return dic

def checkCoOrthologs(candidate_name, best_hit, ref, fdog_ref_species, candidatesOutFile, searchTool, matrix, dataPath, tmp_path):
    ###########getting sequences and write all in one file to make msa #########
    name_file = candidate_name + ".co"
    output_file = tmp_path + name_file + '.fasta'
    aln_file = tmp_path + name_file + '.aln'
    genome_dir_path = dataPath + '/genome_dir/%s/%s.fa'%(fdog_ref_species, fdog_ref_species)
    #print(searchTool)

    out = open(output_file, "w")
    inSeq = SeqIO.to_dict((SeqIO.parse(open(genome_dir_path), 'fasta')))
    out.write(">" + best_hit + "\n")
    out.write(str(inSeq[best_hit].seq) + "\n")
    out.write(">" + ref + "\n")
    out.write(str(inSeq[ref].seq )+ "\n")

    candidates = readFasta(candidatesOutFile)
    for record in candidates:
        if candidate_name in record.id:
            out.write(">" + candidate_name + "\n")
            out.write(str(record.seq) + "\n")
            break

    out.close()

    if searchTool == "muscle":
        os.system("muscle -quiet -in " + output_file + " -out " + aln_file)
        #print("muscle -quiet -in " + output_file + " -out " + aln_file)
    elif searchTool == "mafft-linsi":
        #print("mafft-linsi")
        os.system('mafft --maxiterate 1000 --localpair --anysymbol --quiet ' + output_file + ' > ' + aln_file)

    #d_ref = get_distance(aln_file, best_hit, ref)
    #d = get_distance(aln_file, best_hit, candidate_name)
    distances = get_distance_biopython(aln_file, matrix)

    distance_hit_query = distances[best_hit, candidate_name]
    distance_ref_hit = distances[best_hit, ref]

    if distance_ref_hit < distance_hit_query:
        #accepted
        return 1, distance_ref_hit, distance_hit_query

    else:
        #rejected
        return 0, distance_ref_hit, distance_hit_query

def backward_search(candidatesOutFile, fasta_path, strict, fdog_ref_species, evalue_cut_off, taxa, searchTool, checkCo, msaTool, matrix, dataPath, filter, tmp_path):
    # the backward search uses the genes predicted from augustus and makes a blastp search
    #the blastp search is against all species that are part of the core_ortholog group if the option --strict was chosen or only against the ref taxa
    seedDic = getSeedInfo(fasta_path)
    #print(fasta_path)
    orthologs = []
    #print(seedDic)
    blast_dir_path = dataPath + "/blast_dir/"
    if strict != True:
        seed = [fdog_ref_species]
        try:
            id_ref = seedDic[fdog_ref_species]
        except KeyError:
            print("The fDOG reference species isn't part of the core ortholog group, ... exciting")
            return 0, seed
        if searchTool == "blast":
            os.system("blastp -db " + blast_dir_path + fdog_ref_species + "/" + fdog_ref_species + " -outfmt '6 sseqid qseqid evalue' -max_target_seqs 10 -out " + tmp_path + "blast_" + fdog_ref_species + " -evalue " + str(evalue_cut_off) + " -query " + candidatesOutFile)
        else:
            print("diamonds are the girls best friends")
            ##### diamond call

        alg_file = open(tmp_path + "blast_" + fdog_ref_species, "r")
        lines = alg_file.readlines()
        alg_file.close()
        old_name = None
        min = 10
        for line in lines:
            id, gene, evalue = (line.replace("\n", "")).split("\t")
            gene_name = gene.split("|")[2]
            if gene_name != old_name:
                print("candidate:%s"%(gene_name))
                print("blast-hit:%s"%(id))
                min = float(evalue)
                if id in id_ref:
                    orthologs.append(gene)
                    print("\thitting\n")
                else:
                    if checkCo == True:
                        for i in id_ref:
                            print("Best hit %s differs from reference sequence %s! Doing further checks\n"%(id, i))
                            co_orthologs_result, distance_ref_hit, distance_hit_query = checkCoOrthologs(gene_name, id, i, fdog_ref_species, candidatesOutFile, msaTool, matrix, dataPath, tmp_path)
                            if co_orthologs_result == 1:
                                print("\t Distance query - blast hit: %6.4f, Distance blast hit - reference: %6.4f\tAccepting\n"%(distance_hit_query, distance_ref_hit))
                                orthologs.append(gene)
                            elif co_orthologs_result == 0:
                                print("\t Distance query - blast hit: %6.4f, Distance blast hit - reference: %6.4f\tRejecting\n"%(distance_hit_query, distance_ref_hit))
                    else:
                        print("\tnothitting\n")
            elif (gene_name == old_name) and float(evalue) == min and gene_name not in orthologs:
                if id in id_ref:
                    orthologs.append(gene)
                    print("\thitting\n")
                else:
                    if checkCo == True:
                        for i in id_ref:
                            print("Best hit %s differs from reference sequence %s! Doing further checks\n"%(id, i))
                            co_orthologs_result, distance_ref_hit, distance_hit_query = checkCoOrthologs(gene_name, id, i, fdog_ref_species, candidatesOutFile, msaTool, matrix, dataPath, tmp_path)
                            if co_orthologs_result == 1:
                                print("\t Distance query - blast hit: %6.4f, Distance blast hit - reference: %6.4f\tAccepting\n"%(distance_hit_query, distance_ref_hit))
                                orthologs.append(gene)
                            elif co_orthologs_result == 0:
                                print("\t Distance query - blast hit: %6.4f, Distance blast hit - reference: %6.4f\tRejecting\n"%(distance_hit_query, distance_ref_hit))
                    else:
                        print("\tnot hitting\n")
            old_name = gene_name


        if orthologs == []:
            print("No hit in the backward search, ...exciting")
            return 0, seed

    else:
        if taxa != []:
            seed = taxa
            try:
                i = seed.index(fdog_ref_species)
                seed.insert(0,seed.pop(i))
            except ValueError:
                seed.insert(0,fdog_ref_species)
            #print(seed)
            #print("with taxa list from user input")

        else:
            seed = []
            for key in seedDic:
                if key == fdog_ref_species:
                    seed.insert(0,key)
                else:
                    seed.append(key)

        orthologs = set({})

        for species in seed:
            print("backward search in species " + species + "\n")
            orthologs_new = set({})
            try:
                id_ref = seedDic[species]
            except KeyError:
                print("The species " + species + " isn't part of the core ortholog group, ... exciting")
                return 0, seed

            os.system("blastp -db " + blast_dir_path + species + "/" + species + " -outfmt '6 sseqid qseqid evalue' -max_target_seqs 10 -seg " + filter + " -out " + tmp_path + "/blast_" + species + " -evalue " + str(evalue_cut_off) + " -query " + candidatesOutFile)
            alg_file = open(tmp_path + "/blast_" + species, "r")
            lines = alg_file.readlines()
            alg_file.close()
            old_name = None
            min = 10
            for line in lines:
                id, gene_name, evalue = (line.replace("\n", "")).split("\t")
                if gene_name != old_name:
                    min = float(evalue)
                    if id in id_ref:
                        orthologs_new.add(gene_name)

                elif (gene_name == old_name) and float(evalue) == min:
                    if id in id_ref:
                        orthologs_new.add(gene_name)

            #print(species)
            #print(orthologs_new)
            if species == fdog_ref_species:
                orthologs = orthologs_new
            else:
                orthologs = orthologs & orthologs_new
                if orthologs == {}:
                    print("No ortholog was found with option --strict")
                    return 0, seed



    #print(orthologs)
    return list(orthologs), seed

def addSequences(sequenceIds, candidate_fasta, core_fasta, output, name, species_list, refBool, tmp_path):
    #print("addSequences")
    #print(sequenceIds)
    #print(species_list)
    output_file = open(output, "a+")
    if refBool == False:
        seq_records_core = readFasta(core_fasta)
        seq_records_core = list(seq_records_core)
        for species in species_list:
            for entry_core in seq_records_core:
                if species in entry_core.id:
                    output_file.write(">" + entry_core.id + "\n")
                    output_file.write(str(entry_core.seq) + "\n")

    seq_records_candidate = readFasta(candidate_fasta)
    seq_records_candidate = list(seq_records_candidate)
    for entry_candidate in seq_records_candidate:
        #print(entry_candidate.id)
        #print(sequenceIds)
        if entry_candidate.id in sequenceIds:
            output_file.write(">" + entry_candidate.id + "\n")
            output_file.write(str(entry_candidate.seq) + "\n")
    output_file.close()
    return 0

def createFasInput(orthologsOutFile, mappingFile):
    with open(orthologsOutFile, "r") as f:
        fas_seed_id = (f.readline())[1:-1]

    mappingFile = open(mappingFile, "a+")

    seq_records = readFasta(orthologsOutFile)
    for seq in seq_records:
        ncbi_id = (seq.id.split("@"))[1]
        mappingFile.write(seq.id + "\t" + "ncbi" + ncbi_id + "\n")


    return fas_seed_id

def cleanup(tmp, tmp_path):
    if tmp == False:
        os.system('rm -r ' + tmp_path)

def checkOptions():
    pass
    #muss ich unbedingt noch ergänzen wenn ich alle möglichen input Optionen implementiert habe!!!



def main():

    #################### handle user input ########################################

    version = '0.0.1'

    parser = argparse.ArgumentParser(description='You are running fdog.assembly version ' + str(version) + '.')
    parser.add_argument('--version', action='version', version=str(version))

    required = parser.add_argument_group('Required arguments')
    required.add_argument('--gene', help='Core_ortholog group name. Folder inlcuding the fasta file, hmm file and aln file has to be located in core_orthologs/',
                            action='store', default='', required=True)
    required.add_argument('--augustusRefSpec', help='augustus reference species', action='store', default='', required=True)
    required.add_argument('--refSpec', help='Reference taxon for fDOG.', action='store', default='', required=True)

    optional = parser.add_argument_group('Optional arguments')
    optional.add_argument('--avIntron', help='average intron length of the assembly species in bp (default: 5000)',action='store', default=5000, type=int)
    optional.add_argument('--lengthExtension', help='length extension of the candidate regions in bp (default:5000)', action='store', default=5000, type=int)
    optional.add_argument('--assemblyPath', help='Path for the assembly directory', action='store', default='')
    optional.add_argument('--tmp', help='tmp files will not be deleted', action='store_true', default = False)
    optional.add_argument('--out', help='Output directory', action='store', default='')
    optional.add_argument('--dataPath', help='data directory', action='store', default='')
    optional.add_argument('--coregroupPath', help='core_ortholog directory', action='store', default='')
    optional.add_argument('--searchTool', help='Choose between blast and diamond as alignemnt search tool(default:blast)', action='store', choices=['blast', 'diamond'], default='blast')
    optional.add_argument('--evalBlast', help='E-value cut-off for the Blast search. (default: 0.00001)', action='store', default=0.00001, type=float)
    optional.add_argument('--strict', help='An ortholog is only then accepted when the reciprocity is fulfilled for each sequence in the core set', action='store_true', default=False)
    optional.add_argument('--msaTool', help='Choose between mafft-linsi or muscle for the multiple sequence alignment. DEFAULT: muscle', choices=['mafft-linsi', 'muscle'], action='store', default='muscle')
    optional.add_argument('--checkCoorthologsRef', help='During the final ortholog search, accept an ortholog also when its best hit in the reverse search is not the core ortholog itself, but a co-ortholog of it', action='store_true', default=False)
    optional.add_argument('--scoringmatrix', help='Choose a scoring matrix for the distance criteria used by the option --checkCoorthologsRef. DEFAULT: blosum62', choices=['identity', 'blastn', 'trans', 'benner6', 'benner22', 'benner74', 'blosum100', 'blosum30', 'blosum35', 'blosum40', 'blosum45', 'blosum50', 'blosum55', 'blosum60', 'blosum62', 'blosum65', 'blosum70', 'blosum75', 'blosum80', 'blosum85', 'blosum90', 'blosum95', 'feng', 'fitch', 'genetic', 'gonnet', 'grant', 'ident', 'johnson', 'levin', 'mclach', 'miyata', 'nwsgappep', 'pam120', 'pam180', 'pam250', 'pam30', 'pam300', 'pam60', 'pam90', 'rao', 'risler', 'structure'], action='store', default='blosum62')
    optional.add_argument('--coreTaxa', help='List of core taxa used during --strict', action='store', default='')
    optional.add_argument('--filter', help='Switch the low complexity filter for the blast search on.', action='store', default='no')
    optional.add_argument('--fasoff', help='Turn OFF FAS support', action='store_true', default=False)
    optional.add_argument('--pathFile', help='Config file contains paths to data folder (in yaml format)', action='store', default='')
    optional.add_argument('--searchTaxon', help='Search Taxon name', action='store', default='')
    optional.add_argument('--force', help='An existing extendedn.fa file will not be appended', action='store_true', default=False)

    args = parser.parse_args()

    # required
    group = args.gene
    augustus_ref_species = args.augustusRefSpec
    fdog_ref_species = args.refSpec
    #paths user input
    assemblyDir = args.assemblyPath
    dataPath = args.dataPath
    core_path = args.coregroupPath
    out = args.out
    pathFile = args.pathFile
    #I/O
    tmp = args.tmp
    strict = args.strict
    checkCoorthologs = args.checkCoorthologsRef
    filter = args.filter
    if filter == True or filter == 'yes':
        filter = 'yes'
    else:
        filter = 'no'
    #others
    average_intron_length = args.avIntron
    length_extension = args.lengthExtension
    searchTool = args.searchTool
    evalue = args.evalBlast
    msaTool = args.msaTool
    matrix = args.scoringmatrix
    taxa = args.coreTaxa
    if taxa == '':
        taxa =[]
    else:
        taxa = taxa.split(",")
    fasoff = args.fasoff
    searchTaxon = args.searchTaxon
    force = args.force

    #checking paths
    if dataPath == '':
        fdogPath = os.path.realpath(__file__).replace('/fDOGassembly.py','')
        configFile = fdogPath + '/bin/pathconfig.txt'
        if not os.path.exists(configFile):
            sys.exit('No pathconfig.txt found. Please run fdog.setup (https://github.com/BIONF/fDOG/wiki/Installation#setup-fdog) or give a dataPath')
        if pathFile == '':
            with open(configFile) as f:
                dataPath = f.readline().strip()
        else:
            cfg = load_config(pathFile)
            try:
                dataPath = cfg['dataPath']
            except:
                dataPath = 'config'

    if assemblyDir == '':
        assemblyDir = dataPath + '/assembly_dir/'
    if out == '':
        out = os.getcwd()
    if core_path == '':
        core_path = out + '/core_orthologs/'


    # user input has to be checked here before fDOGassembly continues

    assembly_names = os.listdir(assemblyDir)

    ########################## some variables ##################################

    refBool = False # checks if sequences of reference species were already part of the extended.fa file
    ########### paths ###########

    msa_path = core_path + "/" + group +"/"+ group + ".aln"
    hmm_path = core_path + "/" + group +"/hmm_dir/"+ group + ".hmm"
    fasta_path = core_path + "/" + group +"/"+ group + ".fa"
    consensus_path = out + "/tmp/" + group + ".con"
    profile_path = out + "/tmp/" + group + ".prfl"

    ###################### create tmp folder ###################################

    os.system('mkdir ' + out + '/tmp')

    ######################## consensus sequence ################################

    #make a majority-rule consensus sequence with the tool hmmemit from hmmer
    print("Building a consensus sequence \n")
    os.system('hmmemit -c -o' + consensus_path + ' ' + hmm_path)
    print("consensus sequence is finished\n")

    ######################## block profile #####################################

    print("Building a block profile \n")

    os.system('msa2prfl.pl ' + msa_path + ' --setname=' + group + ' >' + profile_path)
    #print(os.path.getsize(profile_path))
    if int(os.path.getsize(profile_path)) > 0:
        print("block profile is finished \n")
    else:
        print("Building block profiles failed. Using prepareAlign to convert alignment\n")
        new_path = core_path + group +"/"+ group + "_new.aln"
        os.system('prepareAlign < ' + msa_path + ' > ' + new_path)
        os.system('msa2prfl.pl ' + new_path + ' --setname=' + group + ' >' + profile_path)
        print("block profile is finished \n")


    searchBool = False

    for asName in assembly_names:
        if searchBool == True:
            break
        if searchTaxon != '' and searchBool == False:
            asName = searchTaxon
            searchBool = True

        ################### path definitions ###################################
        os.system('mkdir ' + out + '/tmp/' + asName)
        tmp_path = out + "/tmp/" + asName + "/"
        candidatesOutFile = tmp_path + group + ".candidates.fa"
        if searchTaxon != '':
            orthologsOutFile = out + "/" + group + "_" + asName + ".extended.fa"
            fasOutFile = out + "/" + group + "_" + asName
            mappingFile = tmp_path + group + "_" + asName + ".mapping.txt"
        else:
            orthologsOutFile = out + "/" + group + ".extended.fa"
            fasOutFile = out + "/" + group
            mappingFile = out + "/tmp/" + group + ".mapping.txt"


        print("Searching in species " + asName + "\n")
        assembly_path = assemblyDir + "/" + asName + "/" + asName + ".fa"
        db_path = assemblyDir + "/" + asName + "/blast_dir/" + asName + ".fa"
    ######################## tBLASTn ###########################################

    #database anlegen

        db_check = searching_for_db(db_path)
        #print(assembly_path)
        if db_check == 0:
            print("creating a blast data base \n")
            os.system('makeblastdb -in ' + assembly_path + ' -dbtype nucl -parse_seqids -out ' + db_path)
            print("database is finished \n")
        else:
            print('blast data base exists already, continuing...')


    #make a tBLASTn search against the new database
    #codon table argument [-db_gencode int_value], table available ftp://ftp.ncbi.nih.gov/entrez/misc/data/gc.prt

        print("tBLASTn search against data base")
        os.system('tblastn -db ' + db_path + ' -query ' + consensus_path + ' -outfmt "6 sseqid sstart send evalue qstart qend " -out ' + tmp_path + '/blast_results.out')
        print("tBLASTn search is finished")

    ################### search for candidate regions and extract seq ###########

    # parse blast and filter for candiate regions
        regions, number_regions = candidate_regions(average_intron_length, evalue, tmp_path)

        if regions == 0:
            #no candidat region are available, no ortholog can be found
            print("No candidate region found")
            continue

        else:
            print(str(number_regions) + " candiate regions were found. Extracting sequences...")
            extract_seq(regions, db_path, tmp_path)

    ############### make Augustus PPX search ###################################
        print("starting augustus ppx \n")
        augustus_ppx(regions, candidatesOutFile, length_extension, profile_path, augustus_ref_species, asName, group, tmp_path)
        print("augustus is finished \n")

    ################# backward search to filter for orthologs###################
    #verschiede Modi beachten!
        reciprocal_sequences, taxa = backward_search(candidatesOutFile, fasta_path, strict, fdog_ref_species, evalue, taxa, searchTool, checkCoorthologs, msaTool, matrix, dataPath, filter, tmp_path)


        if reciprocal_sequences == 0:
            print("No ortholog fulfilled the reciprocity criteria")
            if searchTaxon == '':
                continue
            else:
                cleanup(tmp)
                return 1

    ################ add sequences to extended.fa in the output folder##########
        addSequences(reciprocal_sequences, candidatesOutFile, fasta_path, orthologsOutFile, group, taxa, refBool, tmp_path)
        refBool = True

    ############### make Annotation with FAS ###################################
        if searchTaxon != '' and fasoff == False:
            fas_seed_id = createFasInput(orthologsOutFile, mappingFile)

            os.system('mkdir ' + tmp_path + 'anno_dir')
            os.system('calcFAS --seed ' + fasta_path + ' --query ' + orthologsOutFile + ' --annotation_dir ' + tmp_path + 'anno_dir --bidirectional --phyloprofile ' + mappingFile + ' --seed_id "' + fas_seed_id + '" --out_dir ' + out + ' --out_name ' + group + '_' + asName )


    if refBool == False and searchTaxon == '':
        print("No orthologs found. Exciting ...")
        cleanup(tmp)
        return 1

    if fasoff == False and searchTaxon == '':
        fas_seed_id = createFasInput(orthologsOutFile, mappingFile)

        os.system('mkdir ' + tmp_path + 'anno_dir')
        os.system('calcFAS --seed ' + fasta_path + ' --query ' + orthologsOutFile + ' --annotation_dir ' + tmp_path + 'anno_dir --bidirectional --tsv --phyloprofile ' + mappingFile + ' --seed_id "' + fas_seed_id + '" --out_dir ' + out + ' --out_name ' + group )


    ################# remove tmp folder ########################################

    cleanup(tmp, tmp_path)


if __name__ == '__main__':
    main()
