#!/usr/bin/env bash

set -eu

if [ -z "$1" ]; then
    echo "Usage: $0 <HANDLE>"
    echo "HANDLE is handle of htb in 5-letter form"
    exit 1
fi
HANDLE="$1"

OFFSET=$(($(date +%s%N) - $(awk '{print int($1*1000000000)}' /proc/uptime)))
export BPFTRACE_PERF_RB_PAGES=512

# bpftrace -e "
# kprobe:htb_enqueue
#  / ((struct Qdisc *)arg1)->handle == 0x$HANDLE /
# {
#     \$qdisc = (struct Qdisc *)arg1;
#     printf(\"%llu,%d,%x\\n\", $OFFSET + nsecs, \$qdisc->q.qlen, \$qdisc->handle);
# }
# kprobe:htb_dequeue
#  / ((struct Qdisc *)arg0)->handle == 0x$HANDLE /
# {
#     \$qdisc = (struct Qdisc *)arg0;
#     printf(\"%llu,%d,%x\\n\", $OFFSET + nsecs, \$qdisc->q.qlen, \$qdisc->handle);
# }
# "

bpftrace -e "
/* Shared map to track the last seen qlen for each handle */
kprobe:htb_enqueue
  / ((struct Qdisc *)arg1)->handle == 0x$HANDLE /
{
    \$q = (struct Qdisc *)arg1;
    \$len = \$q->q.qlen;
    \$h = \$q->handle;

    /* Only print if length CHANGED for this specific handle */
    if (@last_qlen[\$h] != \$len) {
        printf(\"%llu,%d,%x\\n\", $OFFSET + nsecs, \$len, \$h);
        @last_qlen[\$h] = \$len;
    }
}

kprobe:htb_dequeue
  / ((struct Qdisc *)arg1)->handle == 0x$HANDLE /
{
    \$q = (struct Qdisc *)arg0;
    \$len = \$q->q.qlen;
    \$h = \$q->handle;

    if (@last_qlen[\$h] != \$len) {
        printf(\"%llu,%d,%x\\n\", $OFFSET + nsecs, \$len, \$h);
        @last_qlen[\$h] = \$len;
    }
}

/* This block suppresses the final map output */
END {
    clear(@last_qlen);
}
"
