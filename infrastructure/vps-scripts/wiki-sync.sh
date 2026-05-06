#!/bin/bash
exec /home/benjaminbot/.local/bin/rclone copy benjaminos:6-Wiki "$HOME/wiki" --transfers 10 --checkers 20 --fast-list --update --create-empty-src-dirs --stats=10s
