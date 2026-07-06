#!/usr/bin/env bash

set -eu

# info.txt contains multiple lines such as
# sendTCP DL      {Duration_:3s Bytes:0 CCA:search}       52.59.188.110:41549     results/20251206T010542_durationtcp_dl/tcp_dl_search_3000.csv
# dl_ports = 41549
# dl_args = '--tcp-src 41549'
INFO_TXT="$1"
ul_ports="$(grep sendTCP "$INFO_TXT" | grep UL | cut -f 4 | cut -d : -f 2)"
dl_ports="$(grep sendTCP "$INFO_TXT" | grep DL | cut -f 4 | cut -d : -f 2)"

ul_args="$(echo "$ul_ports" | while IFS= read -r port; do echo "--tcp-dst $port"; done | xargs)"
dl_args="$(echo "$dl_ports" | while IFS= read -r port; do echo "--tcp-src $port"; done | xargs)"

# Extract compressed pcaps
INFO_TXT_DIR="$(dirname -- "$INFO_TXT")"

# Exit early
if compgen -G "${INFO_TXT_DIR}/*packets.csv" > /dev/null; then
    echo "Skip ${INFO_TXT_DIR}: some packets.csv files already exist"
    exit 0
fi

local_pcap="${INFO_TXT_DIR}/tcpdump_local.pcap"
remote_pcap="${INFO_TXT_DIR}/tcpdump_remote.pcap"
unzstd -f "${local_pcap}.zst" "${remote_pcap}.zst" 2>/dev/null || true

# Run pcap-match on the UL and DL tests
if [ -n "$ul_ports" ]; then
    pcap-match --name ul $ul_args "$local_pcap" "$remote_pcap"
fi
if [ -n "$dl_ports" ]; then
    pcap-match --name dl $dl_args "$remote_pcap" "$local_pcap"
fi

# Remove the uncompressed pcaps
rm "$local_pcap" "$remote_pcap"

# Rename pcap-match csvs based on netmeas' output name
rename_csvs() {
    direction="$1"
    dir_upper="${direction^^}"
    dir_lower="${direction,,}"
    ports="$2"
    for port in $ports; do
        log_path="$(grep "${dir_upper}.*:${port}" "$INFO_TXT" | cut -f 5)"
        log_name="$(basename -- "$log_path")"
        log_name_short="${log_name%.*}" # remove extension
        (
            cd "$(dirname -- "$INFO_TXT")"
            mv "${dir_lower}.${port}.csv" "${log_name_short}.packets.csv"
        )
    done
}

rename_csvs ul "$ul_ports"
rename_csvs dl "$dl_ports"
