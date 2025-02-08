@echo off

set "IMAGE_NAME=mousoutrade-website"
set "IMAGE_TAG=latest"
set "DOCKERHUB_USERNAME=mousou2011"

echo Tagging image for Docker Hub...
docker tag "%IMAGE_NAME%:%IMAGE_TAG%" "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"

echo Pushing image...
docker push "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"

set "IMAGE_NAME=mousoutrade-engine"

echo Tagging image for Docker Hub...
docker tag "%IMAGE_NAME%:%IMAGE_TAG%" "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"

echo Pushing image...
docker push "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"