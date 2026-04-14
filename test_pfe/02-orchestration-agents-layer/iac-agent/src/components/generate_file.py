"""Generate Terraform configuration files from prompt and repository context."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..models.types import RepositoryContext, TerraformConfiguration, UserRequest


class GenerateFile:
    """Generate Terraform files aligned to provider and resource intent."""

    _SUPPORTED_PROVIDERS = {"aws", "azure", "gcp"}

    def generate(
        self,
        request: UserRequest,
        context: RepositoryContext,
        provider: str,
        resource_hints: Sequence[str],
        rag_context: Sequence[Dict[str, Any]],
    ) -> TerraformConfiguration:
        normalized_provider = provider.lower() if provider else "aws"
        if normalized_provider not in self._SUPPORTED_PROVIDERS:
            normalized_provider = "aws"

        merged_hints = self._merge_hints(resource_hints, rag_context, context, request.text)

        providers_tf = self._build_providers_tf(normalized_provider)
        variables_tf = self._build_variables_tf(normalized_provider, merged_hints)
        main_tf, resources = self._build_main_tf(normalized_provider, merged_hints)
        resources = list(dict.fromkeys(resources))
        outputs_tf = self._build_outputs_tf(normalized_provider, merged_hints)

        combined_hcl = self._combine_hcl(providers_tf, variables_tf, main_tf, outputs_tf)

        return TerraformConfiguration(
            providers_tf=providers_tf,
            variables_tf=variables_tf,
            main_tf=main_tf,
            outputs_tf=outputs_tf,
            provider=normalized_provider,
            resources=resources,
            combined_hcl=combined_hcl,
            metadata={
                "generator": "template",
                "requested": request.text,
                "resource_hints": sorted(merged_hints),
                "rag_pages": [page.get("page_id") or page.get("title") for page in rag_context],
            },
            generation_attempts=1,
            is_valid=False,
        )

    def _merge_hints(
        self,
        resource_hints: Sequence[str],
        rag_context: Sequence[Dict[str, Any]],
        context: RepositoryContext,
        request_text: str,
    ) -> set[str]:
        merged = set(resource_hints)
        query_lower = request_text.lower()

        tag_tokens = {
            "networking": ["vpc", "subnet", "networking", "network"],
            "compute": ["ec2", "vm", "compute"],
            "container": ["container", "ecs", "ecr", "cloud-run", "acr", "artifact-registry"],
            "database": ["database", "rds", "postgres", "sql"],
            "storage": ["storage", "s3", "blob", "bucket", "gcs"],
            "serverless": ["lambda", "function", "serverless"],
            "kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
            "static-site": ["static-site", "cloudfront", "cdn", "website"],
        }

        query_tokens = {
            "networking": ["vpc", "subnet", "network", "firewall", "security group"],
            "compute": ["ec2", "vm", "instance", "compute"],
            "container": ["container", "docker", "ecs", "ecr", "cloud run", "acr"],
            "database": ["database", "rds", "postgres", "mysql", "sql", "cloud sql"],
            "storage": ["storage", "bucket", "s3", "blob", "gcs"],
            "serverless": ["lambda", "function", "serverless"],
            "kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
            "static-site": ["static", "website", "cdn", "cloudfront"],
        }

        for hint in context.detected_resources:
            normalized = hint.strip().lower()
            if normalized:
                merged.add(normalized)

        for page in rag_context:
            tags = [str(tag).lower() for tag in page.get("tags", [])]
            for hint, tokens in tag_tokens.items():
                if not any(token in tags for token in tokens):
                    continue

                if hint in merged:
                    merged.add(hint)
                    continue

                if any(keyword in query_lower for keyword in query_tokens.get(hint, [])):
                    merged.add(hint)

        return merged

    def _build_providers_tf(self, provider: str) -> str:
        if provider == "aws":
            return """terraform {
  required_version = \">= 1.5.0\"
  required_providers {
    aws = {
      source  = \"hashicorp/aws\"
      version = \"~> 5.0\"
    }
  }
}

provider \"aws\" {
  region = var.aws_region
}
"""

        if provider == "azure":
            return """terraform {
  required_version = \">= 1.5.0\"
  required_providers {
    azurerm = {
      source  = \"hashicorp/azurerm\"
      version = \"~> 3.110\"
    }
  }
}

provider \"azurerm\" {
  features {}
}
"""

        return """terraform {
  required_version = \">= 1.5.0\"
  required_providers {
    google = {
      source  = \"hashicorp/google\"
      version = \"~> 5.0\"
    }
  }
}

provider \"google\" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
"""

    def _build_variables_tf(self, provider: str, hints: set[str]) -> str:
        if provider == "aws":
            blocks = [
                """variable \"project_name\" {
  type        = string
  description = \"Project name used for resource naming\"
  default     = \"app\"
}
""",
                """variable \"environment\" {
  type        = string
  description = \"Deployment environment\"
  default     = \"dev\"
}
""",
                """variable \"aws_region\" {
  type        = string
  description = \"AWS region\"
  default     = \"us-east-1\"
}
""",
                """variable \"vpc_cidr\" {
  type        = string
  description = \"CIDR block for VPC\"
  default     = \"10.42.0.0/16\"
}
""",
                """variable \"public_subnet_cidr\" {
  type        = string
  description = \"CIDR block for public subnet\"
  default     = \"10.42.1.0/24\"
}
""",
                """variable \"instance_ami\" {
  type        = string
  description = \"AMI for EC2 instance\"
  default     = \"ami-0c02fb55956c7d316\"
}
""",
                """variable \"instance_type\" {
  type        = string
  description = \"EC2 instance type\"
  default     = \"t3.micro\"
}
""",
            ]

            if "database" in hints:
                blocks.append(
                    """variable \"db_password\" {
  type        = string
  description = \"Database password for demo environments\"
  default     = \"ChangeMe123!\"
  sensitive   = true
}
"""
                )

            if "serverless" in hints:
                blocks.append(
                    """variable \"lambda_package_path\" {
  type        = string
  description = \"Path to Lambda deployment package zip\"
  default     = \"lambda.zip\"
}
"""
                )

            if "kubernetes" in hints:
                blocks.append(
                    """variable \"eks_role_arn\" {
  type        = string
  description = \"IAM role ARN for EKS control plane\"
  default     = \"arn:aws:iam::123456789012:role/eks-control-plane\"
}
"""
                )

            if "container" in hints or "serverless" in hints:
                blocks.append(
                    """variable \"container_image\" {
  type        = string
  description = \"Container image reference\"
  default     = \"public.ecr.aws/docker/library/nginx:1.27\"
}
"""
                )

            return "\n".join(blocks).strip() + "\n"

        if provider == "azure":
            blocks = [
                """variable \"project_name\" {
  type        = string
  description = \"Project name used for resource naming\"
  default     = \"app\"
}
""",
                """variable \"environment\" {
  type        = string
  description = \"Deployment environment\"
  default     = \"dev\"
}
""",
                """variable \"azure_location\" {
  type        = string
  description = \"Azure location\"
  default     = \"East US\"
}
""",
                """variable \"resource_group_name\" {
  type        = string
  description = \"Azure resource group name\"
  default     = \"rg-app-dev\"
}
""",
                """variable \"vm_size\" {
  type        = string
  description = \"Azure VM size\"
  default     = \"Standard_B2s\"
}
""",
                """variable \"admin_password\" {
  type        = string
  description = \"Admin password for VM demo configuration\"
  default     = \"ChangeMe123!\"
  sensitive   = true
}
""",
            ]

            if "container" in hints or "serverless" in hints:
                blocks.append(
                    """variable \"container_image\" {
  type        = string
  description = \"Container image reference\"
  default     = \"mcr.microsoft.com/azuredocs/aci-helloworld\"
}
"""
                )

            return "\n".join(blocks).strip() + "\n"

        blocks = [
            """variable \"project_name\" {
  type        = string
  description = \"Project name used for resource naming\"
  default     = \"app\"
}
""",
            """variable \"environment\" {
  type        = string
  description = \"Deployment environment\"
  default     = \"dev\"
}
""",
            """variable \"gcp_project_id\" {
  type        = string
  description = \"GCP project id\"
  default     = \"my-gcp-project\"
}
""",
            """variable \"gcp_region\" {
  type        = string
  description = \"GCP region\"
  default     = \"us-central1\"
}
""",
            """variable \"gcp_zone\" {
  type        = string
  description = \"GCP zone\"
  default     = \"us-central1-a\"
}
""",
            """variable \"machine_type\" {
  type        = string
  description = \"Compute instance machine type\"
  default     = \"e2-medium\"
}
""",
        ]

        if "container" in hints or "serverless" in hints:
            blocks.append(
                """variable \"container_image\" {
  type        = string
  description = \"Container image reference\"
  default     = \"us-docker.pkg.dev/cloudrun/container/hello\"
}
"""
            )

        return "\n".join(blocks).strip() + "\n"

    def _build_main_tf(self, provider: str, hints: set[str]) -> tuple[str, List[str]]:
        if provider == "aws":
            return self._build_aws_main_tf(hints)
        if provider == "azure":
            return self._build_azure_main_tf(hints)
        return self._build_gcp_main_tf(hints)

    def _build_aws_main_tf(self, hints: set[str]) -> tuple[str, List[str]]:
        resources = [
            "aws_vpc",
            "aws_subnet",
            "aws_security_group",
            "aws_instance",
        ]

        sections = [
            """locals {
  name_prefix = \"${var.project_name}-${var.environment}\"
}
""",
            """resource \"aws_vpc\" \"main\" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${local.name_prefix}-vpc"
    Environment = var.environment
  }
}
""",
            """resource \"aws_subnet\" \"public\" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"

  tags = {
    Name = "${local.name_prefix}-public-subnet"
  }
}
""",
            """resource \"aws_security_group\" \"app\" {
  name        = "${local.name_prefix}-sg"
  description = "Allow HTTP and SSH"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
""",
            """resource \"aws_instance\" \"app\" {
  ami                    = var.instance_ami
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]

  tags = {
    Name = "${local.name_prefix}-instance"
  }
}
""",
        ]

        if "storage" in hints or "static-site" in hints:
            resources.append("aws_s3_bucket")
            sections.append(
                """resource \"aws_s3_bucket\" \"artifacts\" {
  bucket        = "${local.name_prefix}-artifacts"
  force_destroy = true

  tags = {
    Name = "${local.name_prefix}-artifacts"
  }
}
"""
            )

        if "container" in hints:
            resources.extend(["aws_ecr_repository", "aws_ecs_cluster"])
            sections.append(
                """resource \"aws_ecr_repository\" \"app\" {
  name = "${local.name_prefix}-repo"
}

resource \"aws_ecs_cluster\" \"main\" {
  name = "${local.name_prefix}-cluster"
}
"""
            )

        if "database" in hints:
            resources.extend(["aws_db_subnet_group", "aws_db_instance"])
            sections.append(
                """resource \"aws_db_subnet_group\" \"app\" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = [aws_subnet.public.id]
}

resource \"aws_db_instance\" \"app\" {
  identifier             = "${local.name_prefix}-db"
  allocated_storage      = 20
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = "db.t3.micro"
  db_name                = "appdb"
  username               = "appuser"
  password               = var.db_password
  skip_final_snapshot    = true
  db_subnet_group_name   = aws_db_subnet_group.app.name
  vpc_security_group_ids = [aws_security_group.app.id]
}
"""
            )

        if "serverless" in hints:
            resources.extend(["aws_iam_role", "aws_lambda_function"])
            sections.append(
                """resource \"aws_iam_role\" \"lambda_exec\" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource \"aws_lambda_function\" \"app\" {
  function_name = "${local.name_prefix}-fn"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.lambda_handler"
  filename      = var.lambda_package_path
}
"""
            )

        if "kubernetes" in hints:
            resources.append("aws_eks_cluster")
            sections.append(
                """resource \"aws_eks_cluster\" \"main\" {
  name     = "${local.name_prefix}-eks"
  role_arn = var.eks_role_arn

  vpc_config {
    subnet_ids = [aws_subnet.public.id]
  }
}
"""
            )

        if "static-site" in hints:
            resources.extend(["aws_s3_bucket", "aws_cloudfront_distribution"])
            sections.append(
                """resource \"aws_s3_bucket\" \"website\" {
  bucket        = "${local.name_prefix}-website"
  force_destroy = true
}

resource \"aws_cloudfront_distribution\" \"website\" {
  enabled             = true
  default_root_object = "index.html"

  origin {
    domain_name = aws_s3_bucket.website.bucket_regional_domain_name
    origin_id   = "website-origin"
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "website-origin"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
"""
            )

        return "\n".join(sections).strip() + "\n", resources

    def _build_azure_main_tf(self, hints: set[str]) -> tuple[str, List[str]]:
        resources = [
            "azurerm_resource_group",
            "azurerm_virtual_network",
            "azurerm_subnet",
            "azurerm_network_security_group",
            "azurerm_public_ip",
            "azurerm_network_interface",
            "azurerm_linux_virtual_machine",
        ]

        sections = [
            """locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
""",
            """resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.azure_location
}
""",
            """resource "azurerm_virtual_network" "main" {
  name                = "${local.name_prefix}-vnet"
  address_space       = ["10.52.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}
""",
            """resource "azurerm_subnet" "app" {
  name                 = "${local.name_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.52.1.0/24"]
}
""",
            """resource "azurerm_network_security_group" "app" {
  name                = "${local.name_prefix}-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "allow-http"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}
""",
            """resource "azurerm_public_ip" "app" {
  name                = "${local.name_prefix}-pip"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
}
""",
            """resource "azurerm_network_interface" "app" {
  name                = "${local.name_prefix}-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.app.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }
}
""",
            """resource "azurerm_linux_virtual_machine" "app" {
  name                = "${local.name_prefix}-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size
  admin_username      = "azureuser"
  admin_password      = var.admin_password
  disable_password_authentication = false
  network_interface_ids = [azurerm_network_interface.app.id]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }
}
""",
        ]

        if "storage" in hints or "static-site" in hints:
            resources.append("azurerm_storage_account")
            sections.append(
                """resource "azurerm_storage_account" "artifacts" {
  name                     = "${replace(local.name_prefix, "-", "")}art"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}
"""
            )

        if "container" in hints:
            resources.append("azurerm_container_registry")
            sections.append(
                """resource "azurerm_container_registry" "app" {
  name                = "${replace(local.name_prefix, "-", "")}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
}
"""
            )

        if "database" in hints:
            resources.append("azurerm_postgresql_flexible_server")
            sections.append(
                """resource "azurerm_postgresql_flexible_server" "app" {
  name                   = "${local.name_prefix}-pg"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "14"
  administrator_login    = "pgadmin"
  administrator_password = var.admin_password
  zone                   = "1"
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
}
"""
            )

        if "serverless" in hints:
            resources.extend(["azurerm_service_plan", "azurerm_storage_account", "azurerm_linux_function_app"])
            sections.append(
                """resource "azurerm_service_plan" "app" {
  name                = "${local.name_prefix}-plan"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_storage_account" "function" {
  name                     = "${replace(local.name_prefix, "-", "")}fn"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_linux_function_app" "app" {
  name                       = "${local.name_prefix}-fn"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.app.id
  storage_account_name       = azurerm_storage_account.function.name
  storage_account_access_key = azurerm_storage_account.function.primary_access_key

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }
}
"""
            )

        if "kubernetes" in hints:
            resources.append("azurerm_kubernetes_cluster")
            sections.append(
                """resource "azurerm_kubernetes_cluster" "main" {
  name                = "${local.name_prefix}-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "${replace(local.name_prefix, "-", "")}-aks"

  default_node_pool {
    name       = "default"
    node_count = 1
    vm_size    = "Standard_B2s"
  }

  identity {
    type = "SystemAssigned"
  }
}
"""
            )

        if "static-site" in hints:
            resources.append("azurerm_storage_account")
            sections.append(
                """resource "azurerm_storage_account" "website" {
  name                     = "${replace(local.name_prefix, "-", "")}web"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  static_website {
    index_document = "index.html"
    error_404_document = "index.html"
  }
}
"""
            )

        return "\n".join(sections).strip() + "\n", resources

    def _build_gcp_main_tf(self, hints: set[str]) -> tuple[str, List[str]]:
        resources = [
            "google_compute_network",
            "google_compute_subnetwork",
            "google_compute_firewall",
            "google_compute_instance",
        ]

        sections = [
            """locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
""",
            """resource "google_compute_network" "main" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false
}
""",
            """resource "google_compute_subnetwork" "main" {
  name          = "${local.name_prefix}-subnet"
  ip_cidr_range = "10.62.1.0/24"
  region        = var.gcp_region
  network       = google_compute_network.main.id
}
""",
            """resource "google_compute_firewall" "allow_http" {
  name    = "${local.name_prefix}-allow-http"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["80", "22"]
  }

  source_ranges = ["0.0.0.0/0"]
}
""",
            """resource "google_compute_instance" "app" {
  name         = "${local.name_prefix}-vm"
  machine_type = var.machine_type
  zone         = var.gcp_zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    access_config {}
  }

  tags = ["http-server"]
}
""",
        ]

        if "storage" in hints or "static-site" in hints:
            resources.append("google_storage_bucket")
            sections.append(
                """resource "google_storage_bucket" "artifacts" {
  name                        = "${local.name_prefix}-artifacts"
  location                    = var.gcp_region
  force_destroy               = true
  uniform_bucket_level_access = true
}
"""
            )

        if "container" in hints:
            resources.append("google_artifact_registry_repository")
            sections.append(
                """resource "google_artifact_registry_repository" "app" {
  location      = var.gcp_region
  repository_id = "${replace(local.name_prefix, "-", "")}-repo"
  description   = "Container registry repository"
  format        = "DOCKER"
}
"""
            )

        if "database" in hints:
            resources.extend(["google_sql_database_instance", "google_sql_database"])
            sections.append(
                """resource "google_sql_database_instance" "app" {
  name             = "${local.name_prefix}-sql"
  database_version = "POSTGRES_15"
  region           = var.gcp_region

  settings {
    tier = "db-f1-micro"
  }
}

resource "google_sql_database" "app" {
  name     = "appdb"
  instance = google_sql_database_instance.app.name
}
"""
            )

        if "serverless" in hints:
            resources.append("google_cloud_run_v2_service")
            sections.append(
                """resource "google_cloud_run_v2_service" "app" {
  name     = "${local.name_prefix}-run"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.container_image
    }
  }
}
"""
            )

        if "kubernetes" in hints:
            resources.append("google_container_cluster")
            sections.append(
                """resource "google_container_cluster" "main" {
  name               = "${local.name_prefix}-gke"
  location           = var.gcp_region
  initial_node_count = 1
}
"""
            )

        if "static-site" in hints:
            resources.append("google_storage_bucket")
            sections.append(
                """resource "google_storage_bucket" "website" {
  name                        = "${local.name_prefix}-website"
  location                    = var.gcp_region
  force_destroy               = true
  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }
}
"""
            )

        return "\n".join(sections).strip() + "\n", resources

    def _build_outputs_tf(self, provider: str, hints: set[str]) -> str:
        sections: List[str] = []

        if provider == "aws":
            sections.extend(
                [
                    """output "provider" {
  value = "aws"
}
""",
                    """output "vpc_id" {
  value = aws_vpc.main.id
}
""",
                    """output "instance_public_ip" {
  value = aws_instance.app.public_ip
}
""",
                ]
            )
            if "storage" in hints or "static-site" in hints:
                sections.append(
                    """output "artifacts_bucket_name" {
  value = try(aws_s3_bucket.artifacts.bucket, null)
}
"""
                )
            if "container" in hints:
                sections.append(
                    """output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
"""
                )
            if "database" in hints:
                sections.append(
                    """output "database_endpoint" {
  value = aws_db_instance.app.address
}
"""
                )
            if "serverless" in hints:
                sections.append(
                    """output "lambda_function_name" {
  value = aws_lambda_function.app.function_name
}
"""
                )
            if "kubernetes" in hints:
                sections.append(
                    """output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}
"""
                )
            if "static-site" in hints:
                sections.append(
                    """output "cloudfront_domain_name" {
  value = try(aws_cloudfront_distribution.website.domain_name, null)
}
"""
                )

            return "\n".join(sections).strip() + "\n"

        if provider == "azure":
            sections.extend(
                [
                    """output "provider" {
  value = "azure"
}
""",
                    """output "resource_group_name" {
  value = azurerm_resource_group.main.name
}
""",
                    """output "vm_public_ip" {
  value = azurerm_public_ip.app.ip_address
}
""",
                ]
            )
            if "storage" in hints or "static-site" in hints:
                sections.append(
                    """output "storage_account_name" {
  value = try(azurerm_storage_account.artifacts.name, null)
}
"""
                )
            if "container" in hints:
                sections.append(
                    """output "acr_login_server" {
  value = azurerm_container_registry.app.login_server
}
"""
                )
            if "database" in hints:
                sections.append(
                    """output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.app.fqdn
}
"""
                )
            if "serverless" in hints:
                sections.append(
                    """output "function_app_url" {
  value = azurerm_linux_function_app.app.default_hostname
}
"""
                )
            if "kubernetes" in hints:
                sections.append(
                    """output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}
"""
                )
            if "static-site" in hints:
                sections.append(
                    """output "static_website_endpoint" {
  value = try(azurerm_storage_account.website.primary_web_endpoint, null)
}
"""
                )

            return "\n".join(sections).strip() + "\n"

        sections.extend(
            [
                """output "provider" {
  value = "gcp"
}
""",
                """output "network_name" {
  value = google_compute_network.main.name
}
""",
                """output "instance_public_ip" {
  value = google_compute_instance.app.network_interface[0].access_config[0].nat_ip
}
""",
            ]
        )
        if "storage" in hints or "static-site" in hints:
            sections.append(
                """output "artifacts_bucket_name" {
  value = try(google_storage_bucket.artifacts.name, null)
}
"""
            )
        if "container" in hints:
            sections.append(
                """output "artifact_registry_repo" {
  value = google_artifact_registry_repository.app.id
}
"""
            )
        if "database" in hints:
            sections.append(
                """output "sql_instance_connection_name" {
  value = google_sql_database_instance.app.connection_name
}
"""
            )
        if "serverless" in hints:
            sections.append(
                """output "cloud_run_uri" {
  value = google_cloud_run_v2_service.app.uri
}
"""
            )
        if "kubernetes" in hints:
            sections.append(
                """output "gke_cluster_endpoint" {
  value = google_container_cluster.main.endpoint
}
"""
            )
        if "static-site" in hints:
            sections.append(
                """output "website_url" {
  value = try(google_storage_bucket.website.url, null)
}
"""
            )

        return "\n".join(sections).strip() + "\n"

    def _combine_hcl(self, providers_tf: str, variables_tf: str, main_tf: str, outputs_tf: str) -> str:
        return (
            "# providers.tf\n"
            f"{providers_tf.strip()}\n\n"
            "# variables.tf\n"
            f"{variables_tf.strip()}\n\n"
            "# main.tf\n"
            f"{main_tf.strip()}\n\n"
            "# outputs.tf\n"
            f"{outputs_tf.strip()}\n"
        )
