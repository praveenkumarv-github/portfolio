terraform {
  backend "s3" {
    bucket       = "finance-dash-tfstate-875636131680"
    key          = "prod/domain.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}