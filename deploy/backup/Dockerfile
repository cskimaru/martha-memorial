FROM postgres:18.6-bookworm
# Packages are verified by Debian's signatures. Behind a TLS-inspecting proxy, pass its CA as the
# build secret "build_ca" and apt switches to HTTPS through it.
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -f /run/secrets/build_ca ]; then \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list.d/pgdg.list; \
      install -m 0644 /run/secrets/build_ca /tmp/build_ca.crt; \
      echo 'Acquire::https::CAInfo "/tmp/build_ca.crt";' > /etc/apt/apt.conf.d/99build-ca; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates gnupg rclone \
 && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99build-ca /tmp/build_ca.crt
COPY backup.sh restore.sh loop.sh inbox.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/loop.sh /usr/local/bin/inbox.sh \
 # the shared-photo inbox is written here by inbox.sh and read by the media service, both as uid 10001
 && mkdir -p /inbox && chown 10001:10001 /inbox
ENTRYPOINT ["/usr/local/bin/loop.sh"]
