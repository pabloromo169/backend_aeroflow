# Guía: publicar los servicios nativos de `192.168.0.26` vía Traefik

Los servicios **Kafka, NiFi, Dremio y MongoDB** corren de forma **nativa** (sin
Docker) en la máquina `hadoop-virtualbox` (`hadoop@192.168.0.26`). Esta guía
recoge **qué se cambió en cada aplicación** y **la configuración añadida en
Traefik** (host local, contenedor `traefik`) para que sean accesibles por los
dominios `*.monolith.dynamic-dns.net` **igual que antes con los contenedores**.

Se **detuvieron los contenedores Docker** `kafka`, `nifi` y `mongo` del host
local para no duplicar reglas (mismos dominios).

---

## Resumen de la arquitectura final

| Dominio | Servicio nativo (.26) | Tipo Traefik | Puerto interno |
|---|---|---|---|
| `kafka.monolith.dynamic-dns.net` | Kafka (listener EXTERNAL) | **TCP + TLS/SNI** | `9095` |
| `mongodb.monolith.dynamic-dns.net` | MongoDB | **TCP + TLS/SNI** | `27017` |
| `nifi.monolith.dynamic-dns.net` | NiFi (HTTP) | **HTTP + TLS** | `8081` |
| `dremio.monolith.dynamic-dns.net` | Dremio (HTTP) | **HTTP + TLS** | `9047` |

Traefik **termina el TLS** (Let's Encrypt vía `myresolver`) y enruta:
- HTTP → por `Host(...)`
- TCP → por `HostSNI(...)` en el **443** (mismo puerto que ya estaba reenviado
  en el router, sin abrir puertos nuevos).

El contenedor Traefik corre con red `bridge` en el host local y alcanza la LAN
`192.168.0.26` directamente (verificado).

---

## 1. Kafka nativo (`192.168.0.26`)

### 1.1 Qué se cambió

Kafka se arrancaba manualmente (`kafka-server-start.sh &`) sin systemd, con un
único listener `PLAINTEXT://:9092` anunciado como `localhost`.

Se añadió un **listener EXTERNAL** para Traefik, manteniendo el INTERNAL para
uso local (NiFi, Dremio, scripts).

**Fichero `/opt/kafka/config/server.properties`** (backup:
`server.properties.bak.1791719362`):

```properties
# Kafka KRaft - single node (broker + controller)
process.roles=broker,controller
node.id=1
controller.quorum.bootstrap.servers=localhost:9093
controller.quorum.voters=1@localhost:9093

# INTERNAL -> acceso local/directo (NiFi, Dremio, scripts): localhost:9092 sin TLS
# EXTERNAL -> Traefik (TLS+SNI termina en Traefik y reenvia a 9095)
listeners=INTERNAL://:9092,CONTROLLER://:9093,EXTERNAL://:9095
advertised.listeners=INTERNAL://localhost:9092,EXTERNAL://kafka.monolith.dynamic-dns.net:443
listener.security.protocol.map=CONTROLLER:PLAINTEXT,INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT

inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER

num.network.threads=3
num.io.threads=8
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600

log.dirs=/opt/kafka-data
num.partitions=1
num.recovery.threads.per.data.dir=2

offsets.topic.replication.factor=1
share.coordinator.state.topic.replication.factor=1
share.coordinator.state.topic.min.isr=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0
auto.create.topics.enable=true

log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000
```

> **Por qué el listener EXTERNAL anuncia el puerto 443:** el cliente hace
> bootstrap a `kafka.monolith...:443`; Kafka devuelve los metadatos con esa
> dirección, y el cliente reconecta por SNI a Traefik → Kafka:9095. El
> `advertised.listeners` debe coincidir con lo que usa el cliente.

### 1.2 Servicio systemd (`/etc/systemd/system/kafka.service`)

```ini
[Unit]
Description=Apache Kafka (KRaft)
Documentation=https://kafka.apache.org
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hadoop
Group=hadoop
Environment=JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
Environment=KAFKA_HEAP_OPTS=-Xmx1G -Xms512M
ExecStart=/opt/kafka/bin/kafka-server-start.sh /opt/kafka/config/server.properties
ExecStop=/opt/kafka/bin/kafka-server-stop.sh
Restart=on-failure
RestartSec=10
LimitNOFILE=100000

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kafka
```

### 1.3 Reproducir desde cero

```bash
# 1. Backup y editar server.properties (ver arriba)
sudo cp /opt/kafka/config/server.properties /opt/kafka/config/server.properties.bak
sudo nano /opt/kafka/config/server.properties
# 2. Crear /etc/systemd/system/kafka.service (ver arriba)
sudo systemctl daemon-reload && sudo systemctl enable --now kafka
# 3. Verificar
sudo ss -tlnp | grep -E ':9092|:9093|:9095'
```

### 1.4 Cliente externo

```properties
# client.properties
security.protocol=SSL
```

```
kafka.monolith.dynamic-dns.net:443
```

---

## 2. NiFi nativo (`192.168.0.26`)

### 2.1 Qué se cambió

NiFi se ejecutaba a mano (`/opt/nifi/bin/nifi.sh start`). Estaba en **HTTP en el
8081** con usuario único (`hadoop`). Se cambiaron:

- **`nifi.web.proxy.host`** para que NiFi construya bien las URLs detrás del proxy.
- **HTTPS interno** (`8443`) con un keystore self-signed. Motivo: NiFi **no emite
  tokens de API por HTTP** (`409 Access tokens are only issued over HTTPS`), y sin
  token no se puede automatizar el flujo. Traefik termina el TLS público y ahora
  habla **HTTPS** con NiFi (con `serversTransport` inseguro por ser self-signed).
- Un **servicio systemd** (no existía).

**Fichero `/opt/nifi/conf/nifi.properties`** (backups:
`nifi.properties.bak.*`, `nifi.properties.bak.https.*`):

```properties
nifi.web.proxy.host=nifi.monolith.dynamic-dns.net:443
nifi.web.proxy.context.path=
nifi.web.http.port=
nifi.web.https.host=0.0.0.0
nifi.web.https.port=8443
nifi.remote.input.http.enabled=false
nifi.security.keystore=/opt/nifi/conf/keystore.p12
nifi.security.keystoreType=PKCS12
nifi.security.keystorePasswd=nifipass123
nifi.security.keyPasswd=nifipass123
nifi.security.truststore=/opt/nifi/conf/truststore.p12
nifi.security.truststoreType=PKCS12
nifi.security.truststorePasswd=nifipass123
```

> **Importante:** al quitar el puerto HTTP hay que poner
> `nifi.remote.input.http.enabled=false`, o NiFi no arranca con
> `Remote input HTTP is enabled but nifi.web.http.port is not specified`.

### 2.1.1 Generar el keystore (self-signed)

```bash
cd /tmp
sudo openssl req -x509 -newkey rsa:2048 -keyout nifi-key.pem -out nifi-cert.pem \
  -days 3650 -nodes \
  -subj "/CN=nifi.monolith.dynamic-dns.net/OU=monolith/O=homelab/L=Madrid/C=ES" \
  -addext "subjectAltName=DNS:nifi.monolith.dynamic-dns.net,IP:192.168.0.26"
sudo openssl pkcs12 -export -in nifi-cert.pem -inkey nifi-key.pem \
  -out /opt/nifi/conf/keystore.p12 -name nifi -passout pass:nifipass123
sudo cp /opt/nifi/conf/keystore.p12 /opt/nifi/conf/truststore.p12
sudo chown hadoop:hadoop /opt/nifi/conf/keystore.p12 /opt/nifi/conf/truststore.p12
```

> El certificado es self-signed: por eso Traefik usa el `serversTransport` `nifi`
> con `insecureSkipVerify: true` (ver sección 5). El certificado público de cara
> a internet lo emite Let's Encrypt en Traefik, así que el navegador no ve avisos.

### 2.2 Servicio systemd (`/etc/systemd/system/nifi.service`)

`nifi.sh` no genera PID file, así que **no** sirve `Type=forking`. Se usa
`oneshot` + `RemainAfterExit`:

```ini
[Unit]
Description=Apache NiFi
Documentation=https://nifi.apache.org
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=hadoop
Group=hadoop
Environment="JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64"
ExecStart=/opt/nifi/bin/nifi.sh start
ExecStop=/opt/nifi/bin/nifi.sh stop
TimeoutStartSec=300
TimeoutStopSec=300
LimitNOFILE=50000

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable nifi
sudo systemctl start nifi   # tarda ~1-2 min en arrancar
```

### 2.3 Reproducir desde cero

```bash
# 1. Backup y editar nifi.properties (ver 2.1): HTTPS en 8443, sin HTTP,
#    remote.input.http.enabled=false, keystore/truststore p12
# 2. Generar keystore (ver 2.1.1)
# 3. Crear /etc/systemd/system/nifi.service (ver arriba)
sudo systemctl daemon-reload && sudo systemctl enable --now nifi
# 4. Verificar (200 = login page; 400 desde localhost es normal por SNI)
curl -sk -o /dev/null -w "%{http_code}\n" https://localhost:8443/nifi/
```

---

## 3. Dremio nativo (`192.168.0.26`)

Dremio **ya tenía** servicio systemd (`/etc/systemd/system/dremio.service`) y
sirve HTTP en `9047`. **No se modificó su configuración**; solo se publicó vía
Traefik. Usa Zookeeper embebido (2181) y demás puertos internos, que no se
exponen.

---

## 4. MongoDB nativo (`192.168.0.26`)

Instalado en esta tarea. Ver guía detallada:
`GUIDE-mongodb-192.168.0.26.md`. Escucha en `0.0.0.0:27017` con auth.

---

## 5. Configuración de Traefik (host local)

**Fichero `/home/pablo/traefik-docker/dynamic/dynamic.yml`** (config dinámica por
file provider). Se añadieron routers/servicios para los servicios nativos:

```yaml
http:
  serversTransports:
    nifi:
      insecureSkipVerify: true   # NiFi nativo usa certificado self-signed
  routers:
    # --- Servicios nativos en 192.168.0.26 (sin Docker) ---
    nifi-native:
      rule: "Host(`nifi.monolith.dynamic-dns.net`)"
      service: nifi-native-svc
      entryPoints:
        - websecure
      tls:
        certResolver: myresolver
    dremio-native:
      rule: "Host(`dremio.monolith.dynamic-dns.net`)"
      service: dremio-native-svc
      entryPoints:
        - websecure
      tls:
        certResolver: myresolver
  services:
    nifi-native-svc:
      loadBalancer:
        servers:
          - url: "https://192.168.0.26:8443"
        passHostHeader: true
        serversTransport: nifi@file
    dremio-native-svc:
      loadBalancer:
        servers:
          - url: "http://192.168.0.26:9047"
        passHostHeader: true

tcp:
  routers:
    # Kafka nativo: TLS+SNI terminado en Traefik -> listener EXTERNAL (:9095)
    kafka-native:
      rule: "HostSNI(`kafka.monolith.dynamic-dns.net`)"
      entryPoints:
        - websecure
      service: kafka-native-svc
      tls:
        certResolver: myresolver
    # MongoDB nativo: TLS+SNI terminado en Traefik -> :27017
    mongo-native:
      rule: "HostSNI(`mongodb.monolith.dynamic-dns.net`)"
      entryPoints:
        - websecure
      service: mongo-native-svc
      tls:
        certResolver: myresolver
  services:
    kafka-native-svc:
      loadBalancer:
        servers:
          - address: "192.168.0.26:9095"
    mongo-native-svc:
      loadBalancer:
        servers:
          - address: "192.168.0.26:27017"
```

> Sin entrypoints ni puertos nuevos: Kafka y Mongo comparten el **443** con los
> routers HTTP y se distinguen por **SNI**. Los routers de los antiguos
> contenedores ya no existen (contenedores parados), así que no hay conflicto.

### 5.1 DDNS

En `/home/pablo/traefik-docker/data/config.json` (y el `.env`) se añadieron los
subdominios `mongodb.monolith` y `dremio.monolith` al actualizador ChangeIP:

```
monolith,portainer.monolith,immich.monolith,n8n.monolith,portainer.monolith,
copyparty.monolith,kafka.monolith,nifi.monolith,mongodb.monolith,dremio.monolith
```

Aplicar:

```bash
docker restart changeip
```

### 5.2 Aplicar cambios en Traefik

```bash
cd /home/pablo/traefik-docker
python3 -c "import yaml; yaml.safe_load(open('dynamic/dynamic.yml'))"  # validar YAML
docker compose up -d --force-recreate traefik
```

### 5.3 Parar los contenedores Docker equivalentes

```bash
cd /home/pablo/kafka-docker && docker compose down
cd /home/pablo/nifi-docker  && docker compose down
cd /home/pablo/mongo-docker && docker compose down
```

---

## 6. Verificación end-to-end (realizada)

```bash
# HTTP (NiFi / Dremio)
curl -s -o /dev/null -w "nifi %{http_code}\n"   --resolve nifi.monolith.dynamic-dns.net:443:127.0.0.1 -L https://nifi.monolith.dynamic-dns.net/nifi/   # 200
curl -s -o /dev/null -w "dremio %{http_code}\n" --resolve dremio.monolith.dynamic-dns.net:443:127.0.0.1 -L https://dremio.monolith.dynamic-dns.net/ # 200

# Certificados TLS (SNI)
for d in nifi dremio kafka mongodb; do
  echo | openssl s_client -connect 127.0.0.1:443 -servername $d.monolith.dynamic-dns.net 2>/dev/null \
    | openssl x509 -noout -subject
done

# NiFi API autenticada (usuario hadoop / contraseña hadoophadoop)
TOKEN=$(curl -s -X POST "https://nifi.monolith.dynamic-dns.net/nifi-api/access/token" \
  --resolve nifi.monolith.dynamic-dns.net:443:127.0.0.1 \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=hadoop" --data-urlencode "password=hadoophadoop")
curl -s "https://nifi.monolith.dynamic-dns.net/nifi-api/flow/status" \
  --resolve nifi.monolith.dynamic-dns.net:443:127.0.0.1 -H "Authorization: Bearer $TOKEN"

# Kafka por 443 (TLS+SNI)
printf 'security.protocol=SSL\n' > /tmp/c.properties
kafka-topics.sh --bootstrap-server kafka.monolith.dynamic-dns.net:443 \
  --command-config /tmp/c.properties --list

# Mongo por 443 (TLS+SNI)
mongosh "mongodb://admin:<PASSWORD>@mongodb.monolith.dynamic-dns.net/?tls=true&authSource=admin" \
  --eval 'db.runCommand({ping:1})'
```

Resultados obtenidos: NiFi `200`, Dremio `200`, certificados correctos para los
cuatro dominios, token de API de NiFi emitido correctamente, Kafka lista topics
y Mongo responde `{ ok: 1 }`.

---

## 7. Notas y avisos

- **Kafka INTERNAL (`localhost:9092`)** sigue disponible en la propia máquina
  para NiFi/Dremio/scripts (sin TLS).
- **Credenciales de NiFi:** usuario `hadoop`, contraseña `hadoophadoop`
  (single-user auth). Se puede resetear con
  `sudo /opt/nifi/bin/nifi.sh set-single-user-credentials <user> <pass>`.
- **NiFi ahora usa HTTPS interno (8443)** porque la API no emite tokens por HTTP.
  Si en el futuro se quisiera volver a HTTP, habría que reponer
  `nifi.web.http.port=8081`, `nifi.remote.input.http.enabled=true` y quitar el
  `serversTransport`/`https` en Traefik, pero la API dejaría de funcionar por
  proxy.
- **Kafka no tiene autenticación** (listener PLAINTEXT); está expuesto con TLS
  pero sin SASL. Cualquiera que alcance el SNI puede producir/consumir.
- **Clientes externos** de Kafka/Mongo **deben** usar `tls=true` /
  `security.protocol=SSL` y el **hostname** (no la IP), porque Traefik enruta por
  SNI.
- La VM se reinicia por inactividad. Los servicios `mongod`, `kafka`, `nifi` y
  `dremio` están **enabled** en systemd, por lo que arrancan solos.
- Los **contenedores Docker** de kafka/nifi/mongo quedaron parados. Sus
  directorios (`/home/pablo/{kafka,nifi,mongo}-docker`) se conservan; **no
  vuelvas a levantarlos** a la vez que los nativos o habrá routers duplicados
  con la misma regla.
