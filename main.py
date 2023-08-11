#!/usr/bin/python3
# A script to produce client.json files for lwjgl3ify, compatible with vanilla-like launchers
import argparse
import copy
import datetime
import git
import hashlib
import json
import os
import requests
from pathlib import Path

use_dirty_source = False

loaded_libs = []
lib_jsons = []

mavens = [
    "https://maven.minecraftforge.net/",
    "https://oss.sonatype.org/content/repositories/snapshots/",
    "http://jenkins.usrv.eu:8081/nexus/content/groups/public/",
    "https://libraries.minecraft.net/"
]

# Minecraft library format
mc_lib_format = {
    "name": "",
    "downloads": {
        "artifact": {
            "path": "",
            "url": "",
            "sha1": "",
            "size": 0
        }
    }
}

# Download a jar from the mavens, and return the response and source URL
def downloadJar(path, mavens):

    for maven in mavens:
        req = requests.get(maven + path)
        if req.reason == 'OK':
            return (req, maven + path)

# Get a jar or download it if it doesn't exist
def getJar(url, path):

    res = None
    req = None
    if not os.path.exists("libraries/" + path):

        # Attempt download from maven or URL
        if url is None or url == "":
            res = downloadJar(path, mavens)[0].content
        else:
            req = requests.get(url)

        # If the URL doesn't work, use the maven
        if req is None or req.reason != 'OK':
            res = downloadJar(path, mavens)[0].content
        else:
            res = req.content
        
        with open("libraries/" + path, "wb") as jar:
            jar.write(res)
    else:

        print(f"skip downloading {path.split('/')[-1]}")
        res = open("libraries/" + path, "rb").read()

    return res

# Process a patch file, regardless of how much info it has
def processPatchFile(jsonFile):

    print(jsonFile.name)
    text = json.loads(open(jsonFile, 'r').read())

    for lib in text["libraries"]:

        # Parse the library name
        mc_lib = copy.deepcopy(mc_lib_format)
        mc_lib["name"] = lib["name"]

        lib_name = lib["name"].split(":")
        groupId = lib_name[0]
        artifact_id = lib_name[1]
        version = lib_name[2]

        # Don't process duplicates
        if artifact_id in loaded_libs:
            print(f"{artifact_id} already loaded")
            continue
        loaded_libs.append(artifact_id)

        if len(lib_name) == 4:
            fileName = f"{artifact_id}-{version}-{lib_name[3]}.jar"
        else:
            fileName = f"{artifact_id}-{version}.jar"

        # Generate library definition
        print(f"looking for {fileName} ...")

        path = groupId.replace(".", "/") + "/" + artifact_id + "/" + version + "/"
        if not os.path.exists("libraries/" + path):
            os.makedirs("libraries/" + path)

        if lib.get("rules") != None:
            mc_lib["rules"] = lib.get("rules")

        mc_lib["downloads"]["artifact"]["path"] = path + fileName

        # Generate/grab URL
        if lib.get("url") != None:  # Forge Format

            mc_lib["downloads"]["artifact"]["url"] = lib["url"] + path + fileName
        elif lib.get("MMC-absoluteUrl") != None:  # MMC Format

            mc_lib["downloads"]["artifact"]["url"] = lib["MMC-absoluteUrl"]
        elif lib.get("downloads") != None:  # Minecraft Format

            if lib.get("downloads").get("artifact") != None:

                mc_lib["downloads"]["artifact"]["url"] = lib["downloads"]["artifact"]["url"]
            else:

                # Give up parsing, just add raw
                lib_jsons.append(lib)
                continue

        # Get the file for processing
        req = getJar(
            mc_lib["downloads"]["artifact"]["url"], mc_lib["downloads"]["artifact"]["path"])
        
        # If the URL is empty, download it by path
        if mc_lib["downloads"]["artifact"]["url"] == "" or mc_lib["downloads"]["artifact"]["url"] is None:
            downloadJar(mc_lib["downloads"]["artifact"]["path"], mavens)

        mc_lib["downloads"]["artifact"]["size"] = len(req)
        
        if req == None:
            raise Exception(f"[ERROR] JAR {lib} not found")

        mc_lib["downloads"]["artifact"]["sha1"] = hashlib.sha1(req).hexdigest()
        lib_jsons.append(mc_lib)
        
    if text.get("+jvmArgs") != None:
        versionJson["arguments"]["jvm"] = text["+jvmArgs"] + versionJson["arguments"]["jvm"]

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--use-dirty-source", action="store_true", dest="use_dirty_source", help="allow reading from repo with uncommitted changes")
parser.add_argument("-l", "--location", type=str, default="../lwjgl3ify/", help="directory containing lwjgl3ify repo, default ../lwjgl3ify/")
args = parser.parse_args()

# Open the input file and repo, these should fail fast
in_file = open("base.json")
repo = git.Repo(args.location)
repo_dir = Path(args.location)

# Prepare library and output dir
os.makedirs("out", exist_ok=True)
os.makedirs("libraries", exist_ok=True)

# Sanity checks
if repo.bare:
    print(args.location + " is a bare repo! Doublecheck the path.")
    raise SystemExit

if repo.is_dirty() and not use_dirty_source:
    #print(repo.is_dirty + " " + use_dirty_source)
    print(args.location + " has uncommitted changes! Pass -d/--use-dirty-source to ignore.")
    raise SystemExit

# Get the commit sha
rev = repo.head.commit.hexsha[:7]

# Get the tag. If we're just running a tag, we can drop the commit
tag = repo.git.execute(["git", "describe", "--tags"]).split("-")
if len(tag) == 1:
    rev = tag[0]
tag = tag[0]
rev += "-dirty" if use_dirty_source else ""

print("Parsing lwjgl3ify at " + rev)

# Load the base and get editing!
base = json.load(in_file)

# EZ
id = "1.7.10-lwjgl3ify-" + rev
base["id"] = id
base["version"] = id
base["time"] = datetime.datetime.now().isoformat()
base["releaseTime"] = repo.head.commit.authored_datetime.isoformat()

# Add the java9args
# I know prepending is bad form, but come on this is Python nobody cares
#j9args = open(repo_dir.joinpath("java9args.txt"))
#shift = base["arguments"]["jvm"].copy()
#base["arguments"]["jvm"] = j9args.read().splitlines()[:-2] + shift

# Add the libraries

gtnh_maven = "http://jenkins.usrv.eu:8081/nexus/content/groups/public/"

# lwjgl3ify forgepatches
# Get the latest git tag and strip anything after a '-' (either a pre or untagged)
path = f"com/github/GTNewHorizons/lwjgl3ify/{tag}/lwjgl3ify-{tag}-forgePatches.jar"
url = gtnh_maven + path
sha1 = requests.get(url + ".sha1").text
size = requests.head(url).headers["Content-Length"]
forge_patches = {
    "name": f"com.github.GTNewHorizons:lwjgl3ify:{tag}:forgePatches",
    "downloads": {
        "artifact": {
            "path": path,
            "url": url,
            "sha1": sha1,
            "size": size
        }
    }
}
base["libraries"].append(forge_patches)

"""
# net.minecraft.json patch file
nmj = json.load(open(repo_dir.joinpath("prism-libraries/patches/net.minecraft.json")))
base["libraries"].extend(nmj["libraries"])

# net.minecraftforge.json patch file
# These ones don't come with a SHA or size (how rude) so they must be fetched
# Without a SHA, launchers can't check if they're downloaded so they just don't
# schema is group-id:artifact-id:version:optional-extra
# url is {repository}/{group-id-with-slashes}/{artifact-id}/{version}/{artifact-id}-{version}-{optional-extra}.jar
# Note: this assumes that if the gid, aid, name, version, and extra are the same, the file is the same
nmfj = json.load(open(repo_dir.joinpath("prism-libraries/patches/net.minecraftforge.json")))
for lib in nmfj["libraries"]:

    # Only works if we know the repo
    if "url" in lib:

        # Parse
        maven = lib["url"].removesuffix("/")
        group_id = lib["name"].split(":")[0].replace(".", "/")
        artifact_id = lib["name"].split(":")[1]
        version = lib["name"].split(":")[2]
        extra = lib["name"].split(":")[3] if len(lib["name"].split(":")) == 4 else "none"
        filename = f"{artifact_id}-{version}" + (f"-{extra}.jar" if not extra == "none" else ".jar")
        lib_path = f"{group_id}/{artifact_id}/{version}/{filename}"
        local_path = f"libraries/{lib_path}"
        dl_url = f"{maven}/{lib_path}"

        print(f"Parsing {filename}")

        # Download the file
        if not os.path.isfile(local_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(requests.get(dl_url).content)
                print(f"Downloaded {filename}")

        # Get data
        with open(local_path, "rb") as f:
            size = os.path.getsize(local_path)
            sha1 = hashlib.file_digest(f, "sha1").hexdigest()
            lib["downloads"] = {
                "artifact": {
                    "path": lib_path,
                    "url": dl_url,
                    "sha1": sha1,
                    "size": size
                }
            }
base["libraries"].extend(nmfj["libraries"])

# org.lwjgl3.json patch file
# This one is even worse, it doesn't even come with a maven!
# We need to remove the custom URL field
olj = json.load(open(repo_dir.joinpath("prism-libraries/patches/org.lwjgl3.json")))
for lib in olj["libraries"]:
    del lib["MMC-absoluteUrl"]
    # While the library provides direct downloads, they're also available from a maven
    maven = "https://oss.sonatype.org/content/repositories/snapshots/"
    lib["url"] = maven
base["libraries"].extend(olj["libraries"])
"""

patch_dir = repo_dir.joinpath("prism-libraries/patches")
patch_files = os.listdir(patch_dir)

for patch in patch_files:
    if (patch != "me.eigenraven.lwjgl3ify.forgepatches.json"):
        processPatchFile(patch_dir.joinpath(patch))

base["libraries"].extend(lib_jsons)

# Save it
# Output file opens last, so you don't nuke the output if the program fails during processing
out_file = open(f"out/{id}.json", "w")
json.dump(base, out_file, allow_nan=False, indent=4)
print(f"Wrote out/{id}.json")