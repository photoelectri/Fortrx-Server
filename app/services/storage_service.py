import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from app.config import settings
import uuid
from typing import Iterator

def get_s3_client():
    if settings.S3_PROVIDER =="aws":
        return boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY
        )
    else:
        return boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY
        )
    
def ensure_bucket_exists():
    client = get_s3_client()
    try:
        if settings.S3_PROVIDER == "aws":
            client.create_bucket(
                Bucket=settings.S3_BUCKET_NAME,
                CreateBucketConfiguration={
                    "LocationConstraint": settings.S3_REGION
                }
            )
        else:
            client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ["BucketAlreadyOwnedByYou","BucketAlreadyExists"]:
            pass
        else:
            raise
    except EndpointConnectionError:
        if settings.DEPLOY_ENV in {"local", "test"}:
            return
        raise
        
def generate_blob_key(recipient_id:int, prefix: str = "messages"):
    return f"{prefix}/{recipient_id}/{uuid.uuid4()}"

def upload_blob(blob_key:str,data:bytes):
    client = get_s3_client()
    client.put_object(
        Bucket= settings.S3_BUCKET_NAME,
        Key= blob_key,
        Body = data,
        ContentType = "application/octet-stream"
    )
    return blob_key

def upload_blob_file(blob_key: str, path: str, content_type: str = "application/octet-stream"):
    client = get_s3_client()
    client.upload_file(
        Filename=path,
        Bucket=settings.S3_BUCKET_NAME,
        Key=blob_key,
        ExtraArgs={"ContentType": content_type},
    )
    return blob_key

def download_blob(blob_key:str):
    client = get_s3_client()
    response = client.get_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key = blob_key
    )
    return response["Body"].read()

def download_blob_stream(blob_key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    client = get_s3_client()
    response = client.get_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=blob_key,
    )
    body = response["Body"]
    try:
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        body.close()

def delete_blob(blob_key:str):
    client = get_s3_client()
    client.delete_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key = str(blob_key)
    )
