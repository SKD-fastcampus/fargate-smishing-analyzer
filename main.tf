provider "aws" {
  region  = "ap-northeast-2"
  profile = "Admin@aground5"
}

# 1. CloudWatch Log Group (필수: 없으면 Task 실행 실패)
resource "aws_cloudwatch_log_group" "smishing_logs" {
  name              = "/ecs/smishing-analysis"
  retention_in_days = 7
}

# 1. ECS 클러스터 생성
resource "aws_ecs_cluster" "smishing_analysis" {
  name = "smishing-analysis-cluster"
}

# 2. IAM 역할 (Fargate가 S3에 저장하고 로그를 남기기 위함)
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "ecs-task-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# CloudWatch 및 S3 접근 권한 연결 (기본 실행 정책 포함)
resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# SSM Parameter Store 접근 권한 추가 (Secrets)
resource "aws_iam_role_policy" "ecs_task_ssm_policy" {
  name = "ecs-task-ssm-access"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "secretsmanager:GetSecretValue",
          "kms:Decrypt"
        ]
        Resource = [
          aws_ssm_parameter.db_user.arn,
          aws_ssm_parameter.db_password.arn
        ]
      }
    ]
  })
}

# 2-1. SSM Parameters for DB Credentials
resource "aws_ssm_parameter" "db_user" {
  name  = "/smishing-bot/db_user"
  type  = "String"
  value = "admin" # 기본값, 필요시 변수화 가능
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/smishing-bot/db_password"
  type  = "SecureString"
  value = var.db_password
}

# 3-1. S3 Bucket (결과 저장소)
resource "aws_s3_bucket" "smishing_results" {
  bucket_prefix = "smishing-analysis-results-"
  force_destroy = true # 내용물이 있어도 삭제 허용
}

# S3 Public Access Block (퍼블릭 액세스 차단 해제 - ACL은 차단하고 정책은 허용)
resource "aws_s3_bucket_public_access_block" "smishing_results_public_access" {
  bucket = aws_s3_bucket.smishing_results.id

  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

# S3 Bucket Ownership Controls (소유권 설정 - ACL 비활성화)
resource "aws_s3_bucket_ownership_controls" "smishing_results_ownership" {
  bucket = aws_s3_bucket.smishing_results.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# S3 Bucket Policy (퍼블릭 읽기 권한 부여)
resource "aws_s3_bucket_policy" "smishing_results_policy" {
  bucket = aws_s3_bucket.smishing_results.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.smishing_results.arn}/*"
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.smishing_results_public_access]
}

resource "aws_s3_bucket_cors_configuration" "smishing_results_cors" {
  bucket = aws_s3_bucket.smishing_results.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://detective-crab.vercel.app"]
    expose_headers  = ["ETag"]
  }
}

# 3-2. IAM Policy for S3 Access (Task Role)
resource "aws_iam_role_policy" "ecs_task_s3_policy" {
  name = "ecs-task-s3-access"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.smishing_results.arn,
          "${aws_s3_bucket.smishing_results.arn}/*"
        ]
      }
    ]
  })
}

# 3-3. ECR Repository 생성 (이미지 저장소)
# Terraform은 저장소(그릇)만 만들고, 실제 이미지는 push.sh 스크립트로 올립니다.
resource "aws_ecr_repository" "smishing_repo" {
  name                 = "smishing-bot"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # 이미지가 있어도 삭제 허용

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 4. Fargate 작업 정의 (Task Definition)
resource "aws_ecs_task_definition" "smishing_task" {
  family                   = "smishing-analyzer"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"  # 0.5 vCPU
  memory                   = "1024" # 1GB RAM
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "analyzer"
      image     = "${aws_ecr_repository.smishing_repo.repository_url}:latest"
      essential = true
      environment = [
        { name = "TARGET_URL", value = "" },  # Run-time Override
        { name = "USER_ID", value = "" },     # Run-time Override
        { name = "PRIMARY_KEY", value = "" }, # Run-time Override
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.smishing_results.bucket },
        { name = "DB_HOST", value = "fastcampus-database-1.cpvdwxcchmhy.ap-northeast-2.rds.amazonaws.com" }, # RDS Endpoint로 교체 필요
        { name = "DB_NAME", value = "seogodong" },
        { name = "DB_PORT", value = "3306" }
      ]
      secrets = [
        { name = "DB_USER", valueFrom = aws_ssm_parameter.db_user.arn },
        { name = "DB_PASSWORD", valueFrom = aws_ssm_parameter.db_password.arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/smishing-analysis"
          "awslogs-region"        = "ap-northeast-2"
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# 4. Variables Definition
variable "vpc_id" {
  description = "The ID of the VPC"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the task"
  type        = list(string)
}

variable "db_password" {
  description = "The password for the RDS database"
  type        = string
  sensitive   = true
}

# 5. Security Group (Integrated from template)
data "aws_security_group" "rds_sg" {
  name = "rds-ec2-1"
}

resource "aws_security_group" "fargate_sg" {
  name        = "smishing-analysis-sg"
  description = "Allow only web traffic for analysis"
  vpc_id      = var.vpc_id

  # RDS 접근 허용
  egress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [data.aws_security_group.rds_sg.id]
  }

  # 나가는 트래픽: HTTP, HTTPS만 허용 (데이터 유출 및 스캔 방지)
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 6. Capacity Providers (Fargate Spot 사용 설정)
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.smishing_analysis.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE_SPOT"
  }
}
# 7. EC2에서 Fargate를 실행하기 위한 IAM Role
resource "aws_iam_role" "ec2_ecs_runner_role" {
  name = "ec2-ecs-runner-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ec2_ecs_runner_policy" {
  name = "ec2-ecs-runner-policy"
  role = aws_iam_role.ec2_ecs_runner_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [
          aws_ecs_task_definition.smishing_task.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeTasks",
          "ecs:ListTasks"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution_role.arn
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_ecs_runner_profile" {
  name = "ec2-ecs-runner-profile"
  role = aws_iam_role.ec2_ecs_runner_role.name
}

# 8. Outputs
output "s3_bucket_url" {
  description = "The public endpoint URL of the S3 bucket"
  value       = "https://${aws_s3_bucket.smishing_results.bucket}.s3.${data.aws_region.current.id}.amazonaws.com"
}

data "aws_region" "current" {}
