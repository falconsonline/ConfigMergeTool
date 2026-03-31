usage: ConfigMergeTool.py [-h] --base-dir BASE_DIR --release-dirs RELEASE_DIRS [RELEASE_DIRS ...] --output-dir OUTPUT_DIR
                          [--exclude-params-in-baseonlyconfig] [--dry-run] [--verbose] [--mapping-file MAPPING_FILE]
                          [--copy-baseonlyconfigfile COPY_BASEONLYCONFIGFILE]
 
options:
  -h, --help            show this help message and exit
  --base-dir BASE_DIR
  --release-dirs RELEASE_DIRS [RELEASE_DIRS ...]
  --output-dir OUTPUT_DIR
  --exclude-params-in-baseonlyconfig
                        Exclude parameters present only in base config
  --dry-run
  --verbose
  --mapping-file MAPPING_FILE
                        Optional base-to-release file mapping
  --copy-baseonlyconfigfile COPY_BASEONLYCONFIGFILE
                        List of base files to copy directly without processing

Sample example: 
python3 ConfigMergeTool.py --base-dir base --release-dirs release --output-dir output --copy-baseonlyconfigfile  copy-only-file-test.txt --mapping-file mapping-file-test.txt --verbose
 
base:  is site config directory
release:  is new release config directory
output:  is new merged config directory
 

Sample Files for the optional commands:
----------------------------------------
 
a) sample  *copy-baseonlyconfigfile*   (list of files to be copied as is from production/base. No validation)

copy-only-file-test.txt
========================
base/conf/ten/test1.cfg
base/conf/ten/test2.cfg
 

b) sample  *mapping-file*   (list of files from site/base config which has a different name from release file name. Once this mapping is done merging will be done based comparing these files)
 
mapping-file-test.txt
======================
base/sample1.xml=release/exam/sample.xml
 
 
Note: Logic for Merging is as below:
a) Search for files from base dir recursively in release dir. (Search is done based on filename).
b) If found, create merged config in output dir (keeping site relataive path as base) with release name as new merged file name.
c) if not found add details in xls and log of no mapping file found
d) log similar list of files from release not mapped in xls
e) xls has below sheets
      1) Changes sheet-> This lists all changes done from site/base config with release config into merged config. 
       2) BaseOnlyFiles sheet -> This lists all files present in base dir but not in release dir. (It can happen site and release has different names. In such scenario add the mapping in mapping file.
       3) ReleaseOnlyFiles sheet -> This lists all files present in release dir but not in base dir.
 