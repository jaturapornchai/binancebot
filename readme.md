### Build & Push Command

docker buildx build --platform linux/amd64 -t jaturapornchai/getspot:latest --push .

```
docker build -t  jaturapornchai/getspot .

docker push jaturapornchai/getspot
```


### Deploy Command
```
ssh root@178.128.55.234
password : 19682511

cd /mnt/volume_sgp1_02/jeadbot

sudo docker pull jaturapornchai/getspot:latest

sudo docker-compose up -d

-- ดูการทำงาน
sudo docker logs -f jeadspotbot

-- หยุดทำงาน
sudo docker-compose stop
```

docker build -t binancebot .
docker run -it binancebot

FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il
nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt


API Key
FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il
Secret Key
nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt


api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
