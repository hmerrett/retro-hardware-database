FROM alpine:3.20
RUN apk add --no-cache restic rsync openssh-client tzdata
COPY pull-backup.sh /usr/local/bin/pull-backup
RUN chmod +x /usr/local/bin/pull-backup
ENTRYPOINT ["/usr/local/bin/pull-backup"]
CMD ["schedule"]
