
build: build-backend build-discord

build-backend:
	docker buildx build --platform linux/amd64 backend --tag registry-starfallmc.danya02.ru/interview-manager/back:v1 --builder local --push

build-discord:
	docker buildx build --platform linux/amd64 discordbot --tag registry-starfallmc.danya02.ru/interview-manager/discord:v1 --builder local --push

all: build deploy


deploy: deploy-secrets deploy-svc deploy-backend deploy-discord

deploy-backend:
	kubectl apply -f deploy-backend.yaml

deploy-discord:
	kubectl apply -f deploy-discord.yaml

deploy-svc:
	kubectl apply -f deploy-svc.yaml

deploy-secrets:
	kubectl apply -f secrets.yaml

delete:
	kubectl delete -f deploy-svc.yaml -f deploy-backend.yaml -f deploy-discord.yaml -f secrets.yaml

redeploy:
	kubectl delete -f deploy-backend.yaml -f deploy-discord.yaml
	make build
	kubectl apply  -f deploy-backend.yaml -f deploy-discord.yaml
	

initialize_ns:
	kubectl create namespace buildkit

initialize_builder:
	docker buildx create --bootstrap --name=kube --driver=kubernetes --platform=linux/amd64 --node=builder-amd64 --driver-opt=namespace=buildkit,nodeselector="kubernetes.io/arch=amd64"
	docker buildx create --append --bootstrap --name=kube --driver=kubernetes --platform=linux/arm64 --node=builder-arm64 --driver-opt=namespace=buildkit,nodeselector="kubernetes.io/arch=arm64"

delete_builder:
	docker buildx rm kube
