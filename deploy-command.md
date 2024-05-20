Build & Push Command

```
docker build -t  jaturapornchai/getspot .

docker push jaturapornchai/getspot
```


Deploy Command
```
ssh root@178.128.55.234

cd /mnt/volume_sgp1_02/jeadbot

sudo docker pull jaturapornchai/getspot:latest

sudo docker-compose up -d

sudo docker logs -f jeadjeadspotbot

```