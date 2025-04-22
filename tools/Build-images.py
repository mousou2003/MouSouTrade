import os
import shutil
import subprocess
from dotenv import dotenv_values

# Load environment variables from .env file
if not os.path.exists('.env'):
    print(".env file not found.")
    exit(1)

env_vars = dotenv_values('.env')
APP_CODE_PATHS = env_vars.get("APP_CODE_PATHS", "")
DOCKERHUB_USERNAME = env_vars.get("DOCKERHUB_USERNAME", "")
WEBSITE_IMAGE_NAME = env_vars.get("WEBSITE_IMAGE_NAME", "")
APP_IMAGE_NAME = env_vars.get("APP_IMAGE_NAME", "")

if not APP_CODE_PATHS:
    print("APP_CODE_PATHS is not defined in .env.")
    exit(1)

# Create staging directory
STAGING_DIR = os.path.join(".", "build", "staging")
print(f"APP_CODE_PATHS={APP_CODE_PATHS}")
print("Creating staging directory...")
if os.path.exists(STAGING_DIR):
    shutil.rmtree(STAGING_DIR)
os.makedirs(STAGING_DIR)

# Copy each directory separately
for path in APP_CODE_PATHS.split(","):
    src = os.path.join(".", path.strip())
    dest = os.path.join(STAGING_DIR, path.strip())
    if os.path.exists(src):
        print(f"Copying {src} to staging...")
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        print(f"Error: Directory {src} not found")
        exit(1)

# Copy the "app" directory
app_src = os.path.join(".", "app")
if os.path.exists(app_src):
    print(f"Copying {app_src} to staging...")
    shutil.copytree(app_src,STAGING_DIR, dirs_exist_ok=True)
else:
    print("Error: Directory ./app not found")
    exit(1)

print("All directories copied to staging.")

# Build images
print("Building images...")
os.environ["DOCKER_BUILDKIT"] = "1"
result = subprocess.run(
    ["docker", "compose", "--env-file", ".env", "-f", "./tools/docker-compose-build.yml", "--project-directory", ".", "build"],
    check=False
)
if result.returncode != 0:
    print("Failed to build images.")
    exit(result.returncode)

# Clean up staging directory
shutil.rmtree(STAGING_DIR)
print("Images built successfully.")

# Verify images were created
print("Verifying images...")
for image in [(DOCKERHUB_USERNAME, WEBSITE_IMAGE_NAME), (DOCKERHUB_USERNAME, APP_IMAGE_NAME)]:
    image_name = f"{image[0]}/{image[1]}:latest"
    result = subprocess.run(["docker", "image", "inspect", image_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        print(f"{image[1]} image build failed.")
        exit(1)

print("All images built and verified successfully.")
