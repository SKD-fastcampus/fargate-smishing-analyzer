provider "aws" {
  region  = "ap-northeast-2"
  profile = "Admin@aground5"
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
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# CloudWatch 및 S3 접근 권한 연결 (기본 실행 정책 포함)
resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# 3-1. S3 Bucket (결과 저장소)
resource "aws_s3_bucket" "smishing_results" {
  bucket_prefix = "smishing-analysis-results-"
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
      image     = "${aws_ecr_repository.smishing_repo.repository_url}:latest" # ECR URL 동적 참조
      essential = true
      environment = [
        { name = "TARGET_URL", value = "" }, # 실행 시 주입
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.smishing_results.bucket }
      ]
      log_configuration = {
        log_driver = "awslogs"
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

# 5. Security Group (Integrated from template)
resource "aws_security_group" "fargate_sg" {
  name        = "smishing-analysis-sg"
  description = "Allow only web traffic for analysis"
  vpc_id      = var.vpc_id

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

# 7. ECS Service (Fargate Spot으로 실행)
resource "aws_ecs_service" "main" {
  name            = "smishing-service"
  cluster         = aws_ecs_cluster.smishing_analysis.id
  task_definition = aws_ecs_task_definition.smishing_task.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
  }

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.fargate_sg.id]
    assign_public_ip = true
  }
}