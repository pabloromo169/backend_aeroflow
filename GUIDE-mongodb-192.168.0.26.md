# Guía: MongoDB 8.2 nativo en `192.168.0.26` (Hadoop VM)

Instalación de MongoDB **sin Docker** en la máquina `hadoop-virtualbox`
(`hadoop@192.168.0.26`, Ubuntu 26.04 "Resolute Raccoon", kernel 7.0.0-34-generic),
con autenticación activada y expuesta a internet a través de Traefik
(`mongodb.monolith.dynamic-dns.net`).

---

## 1. Contexto y decisión de versión

- Ubuntu 26.04 usa **kernel 7.0**, que es incompatible con MongoDB **8.0+**
  (bug de TCMalloc/rseq: `MongoDB cannot start: Linux kernel versions 6.19 and newer...`).
  Referencia: <https://jira.mongodb.org/browse/SERVER-121912>.
- El repositorio oficial de MongoDB **no publica `mongodb-org-server` para `resolute`**
  (solo herramientas Atlas). Se usa el repo de **`noble`**.
- **8.3.x y 9.x también fallan** en Ubuntu 26.04; la rama que funciona es **8.2.x**
  (ver SERVER-136272). Por eso se instaló **8.2.12**.

---

## 2. Instalación (pasos reproducibles)

Todos los comandos se ejecutan por SSH en `192.168.0.26`.

### 2.1 Descargar e instalar el servidor

```bash
cd /tmp
curl -fsSL -O \
  "https://repo.mongodb.org/apt/ubuntu/dists/noble/mongodb-org/8.2/multiverse/binary-amd64/mongodb-org-server_8.2.12_amd64.deb"
sudo apt-get install -y ./mongodb-org-server_8.2.12_amd64.deb
```

Dependencias (ya presentes en 26.04): `libc6`, `libcurl4t64`, `libgcc-s1`,
`libssl3t64`, `adduser`, `tzdata`.

### 2.2 Instalar el shell `mongosh`

```bash
cd /tmp
curl -fsSL -O \
  "https://repo.mongodb.org/apt/ubuntu/dists/noble/mongodb-org/8.0/multiverse/binary-amd64/mongodb-mongosh_2.13.0_amd64.deb"
sudo apt-get install -y ./mongodb-mongosh_2.13.0_amd64.deb
```

---

## 3. Configuración de `mongod`

Fichero `/etc/mongod.conf` (se hizo copia de seguridad previa):

```yaml
# mongod.conf - MongoDB 8.2 (nativo, Ubuntu 26.04 / kernel 7.0)
storage:
  dbPath: /var/lib/mongodb

systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log

net:
  port: 27017
  bindIp: 0.0.0.0       # escucha en todas las interfaces (Traefik lo enruta)

processManagement:
  timeZoneInfo: /usr/share/zoneinfo

security:
  authorization: enabled  # requiere usuario/password
```

> **Nota:** no incluir `storage.wiredTiger:` vacío; MongoDB 8.2 lo rechaza con
> `Unrecognized option: storage.wiredTiger`.

---

## 4. Arranque y creación del usuario root

```bash
sudo systemctl enable mongod
sudo systemctl restart mongod
sudo systemctl is-active mongod     # -> active
```

Crear el usuario administrador (solo posible por el "localhost exception",
antes de tener usuarios):

```bash
MONGO_PW=$(openssl rand -base64 18 | tr -d "/+=" | head -c 20)
mongosh --quiet --host 127.0.0.1 --port 27017 --eval \
  'db.getSiblingDB("admin").createUser({user:"admin",pwd:"'"$MONGO_PW"'",roles:[{role:"root",db:"admin"}]})'

# La password se guardó en:
echo "$MONGO_PW" | sudo tee /root/.mongo_admin_pw >/dev/null
sudo chmod 600 /root/.mongo_admin_pw
```

Verificar login:

```bash
mongosh --quiet --host 127.0.0.1 -u admin -p "$(sudo cat /root/.mongo_admin_pw)" \
  --authenticationDatabase admin --eval 'db.runCommand({ping:1})'
# -> { ok: 1 }
```

> La password generada se almacenó en `/root/.mongo_admin_pw` (root-only).
> Cámbiala si lo necesitas con `db.changeUserPassword("admin", "nueva")`.

---

## 5. Publicación a internet en `mongodb.monolith.dynamic-dns.net`

MongoDB habla el protocolo binario de Mongo (no HTTP), por lo que **no se usa un
router HTTP**. Se publica con un **router TCP + TLS/SNI en Traefik** (host local,
contenedor `traefik`), reutilizando el **puerto 443** ya reenviado en el router.
Ver la otra guía (`GUIDE-traefik-servicios-nativos-192.168.0.26.md`) para el detalle.

Resultado:

```bash
# Handshake TLS con SNI correcto
openssl s_client -connect mongodb.monolith.dynamic-dns.net:443 \
  -servername mongodb.monolith.dynamic-dns.net
# subject=CN = mongodb.monolith.dynamic-dns.net ; Verify return code: 0 (ok)
```

Cliente (sin indicar puerto, usa 443 por defecto en TLS):

```
mongodb://admin:<PASSWORD>@mongodb.monolith.dynamic-dns.net/?tls=true&authSource=admin
```

> **Requisitos del cliente:** `tls=true` y usar el **hostname** (para enviar el SNI).
> Si se conecta por IP, Traefik no puede enrutar y falla el handshake.

---

## 6. Resumen de rutas en la máquina

| Elemento | Valor |
|---|---|
| Paquete | `mongodb-org-server 8.2.12` (repo `noble`) |
| Binario | `/usr/bin/mongod` |
| Config | `/etc/mongod.conf` |
| Datos | `/var/lib/mongodb` |
| Log | `/var/log/mongodb/mongod.log` |
| Servicio | `mongod.service` (enabled, active) |
| Escucha | `0.0.0.0:27017` |
| Auth | `authorization: enabled`, usuario `admin` (rol `root`) |
| Password | `/root/.mongo_admin_pw` |
| URL pública | `mongodb.monolith.dynamic-dns.net` (443 vía Traefik) |

---

## 7. Verificación rápida

```bash
# en 192.168.0.26
systemctl is-active mongod
mongosh --quiet -u admin -p "$(sudo cat /root/.mongo_admin_pw)" \
  --authenticationDatabase admin --eval 'db.runCommand({ping:1})'

# desde cualquier equipo con acceso a internet
mongosh "mongodb://admin:<PASSWORD>@mongodb.monolith.dynamic-dns.net/?tls=true&authSource=admin" \
  --eval 'db.runCommand({ping:1})'
```

---

## 8. Aviso

La máquina de VirtualBox se reinicia por inactividad; los tres servicios
(`mongod`, `kafka`, `nifi`, `dremio`) están **habilitados** en systemd, así que
se levantan solos al arrancar la VM.
