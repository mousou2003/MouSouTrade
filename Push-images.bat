@echo off

set "IMAGE_NAME=mousoutrade-website"
set "IMAGE_TAG=latest"
set "DOCKERHUB_USERNAME=mousou2011"

echo Tagging image for Docker Hub...
docker tag "%IMAGE_NAME%:%IMAGE_TAG%" "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"

echo Pushing image...
docker push "%DOCKERHUB_USERNAME%/%IMAGE_NAME%:%IMAGE_TAG%"

REM Add the dynamodb-local image
set "DYNAMODB_IMAGE_NAME=amazon/dynamodb-local"
set "DYNAMODB_IMAGE_TAG=latest"

echo Tagging DynamoDB Local image for Docker Hub...
docker tag "%DYNAMODB_IMAGE_NAME%:%DYNAMODB_IMAGE_TAG%" "%DOCKERHUB_USERNAME%/%DYNAMODB_IMAGE_NAME%:%DYNAMODB_IMAGE_TAG%"

echo Pushing DynamoDB Local image...
docker push "%DOCKERHUB_USERNAME%/%DYNAMODB_IMAGE_NAME%:%DYNAMODB_IMAGE_TAG%"

echo Done.