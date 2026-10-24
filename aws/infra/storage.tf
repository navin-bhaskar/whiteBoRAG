# Ingest storage: one DynamoDB table for projects, captures, links and todos (spec §5),
# and an S3 Vectors index holding one embedding per board section (spec §4.8).

resource "aws_dynamodb_table" "main" {
  name         = "whiteborag"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }
}

resource "aws_s3vectors_vector_bucket" "main" {
  vector_bucket_name = "whiteborag-vectors"
}

resource "aws_s3vectors_index" "captures" {
  vector_bucket_name = aws_s3vectors_vector_bucket.main.vector_bucket_name
  index_name         = "captures"
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"

  # Returned with results but not filterable; `text` would exceed the filterable metadata limit.
  metadata_configuration {
    non_filterable_metadata_keys = ["capture_id", "s3_key", "text"]
  }
}
