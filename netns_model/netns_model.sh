#!/usr/bin/env bash

set -eu

# Configuration
H1_NS=h1
DISH_NS=dish
SAT_NS=sat
POP_NS=pop
H2_NS=h2

# UL: uplink. i.e., from H1 to H2 direction
H1_UL=h1_ul
DISH_DL=dish_dl
DISH_UL=dish_ul
SAT_DL=sat_dl
SAT_UL=sat_ul
POP_DL=pop_dl
POP_UL=pop_ul
H2_DL=h2_dl

# Helper function to run commands inside a namespace
exec_ns() {
    local ns=$1
    shift
    ip netns exec "$ns" "$@"
}

teardown() {
    echo "Tearing down environment..."
    for ns in $H1_NS $DISH_NS $SAT_NS $POP_NS $H2_NS; do
        if ip netns list | grep -q "^$ns"; then
            ip netns del "$ns"
        fi
    done
    echo "Teardown complete."
}

setup() {
    # Ensure clean slate
    teardown

    echo "Setting up network environment..."

    # 1. Create Namespaces
    for ns in $H1_NS $DISH_NS $SAT_NS $POP_NS $H2_NS; do
        ip netns add "$ns"
        exec_ns "$ns" ip link set lo up
    done

    # 2. Create VETH pairs
    # Link: H1 <-> Dishy
    ip link add $H1_UL type veth peer name $DISH_DL qlen 100 
    ip link set dev $H1_UL qlen 100 # TODO: move 
    ethtool -K $H1_UL gso off tso off gro off # TODO: move 
    ip link set $H1_UL netns $H1_NS
    ip link set $DISH_DL netns $DISH_NS

    # Link: Dishy <-> Satellite
    ip link add $DISH_UL type veth peer name $SAT_DL qlen 100
    ip link set $DISH_UL netns $DISH_NS
    ip link set $SAT_DL netns $SAT_NS

    # Link B: Satellite <-> PoP
    ip link add $SAT_UL type veth peer name $POP_DL
    ip link set $SAT_UL netns $SAT_NS
    ip link set $POP_DL netns $POP_NS

    # Link C: PoP <-> H2
    ip link add $POP_UL type veth peer name $H2_DL
    ethtool -K $H2_DL gso off tso off gro off
    ip link set $POP_UL netns $POP_NS
    ip link set $H2_DL netns $H2_NS

    # 3. Configure IPs and Routing
    
    # --- Host 1 Configuration ---
    exec_ns $H1_NS ip addr add 10.0.0.1/24 dev $H1_UL
    exec_ns $H1_NS ip link set $H1_UL up
    exec_ns $H1_NS ip route add default via 10.0.0.2
    # By default, veth has txqueuelen of 1000 and noqueue qdisc
    # exec_ns $H1_NS tc qdisc add dev $H1_UL root pfifo limit 100

    # --- Dishy Configuration ---
    exec_ns $DISH_NS sysctl -w net.ipv4.ip_forward=1 > /dev/null
    exec_ns $DISH_NS ip addr add 10.0.0.2/24 dev $DISH_DL
    exec_ns $DISH_NS ip addr add 10.0.1.1/24 dev $DISH_UL
    exec_ns $DISH_NS ip link set $DISH_DL up
    exec_ns $DISH_NS ip link set $DISH_UL up
    # Route to H2 network via R2
    # exec_ns $DISH_NS ip route add default via 10.0.1.2
    exec_ns $DISH_NS ip route add 10.0.2.0/24 via 10.0.1.2
    exec_ns $DISH_NS ip route add 10.0.3.0/24 via 10.0.1.2

    # --- Satellite Configuration ---
    exec_ns $SAT_NS sysctl -w net.ipv4.ip_forward=1 > /dev/null
    exec_ns $SAT_NS ip addr add 10.0.1.2/24 dev $SAT_DL
    exec_ns $SAT_NS ip addr add 10.0.2.1/24 dev $SAT_UL
    exec_ns $SAT_NS ip link set $SAT_DL up
    exec_ns $SAT_NS ip link set $SAT_UL up
    # Route to H2 network via R2
    exec_ns $SAT_NS ip route add 10.0.0.0/24 via 10.0.1.1
    exec_ns $SAT_NS ip route add 10.0.3.0/24 via 10.0.2.2

    # --- PoP Configuration ---
    exec_ns $POP_NS sysctl -w net.ipv4.ip_forward=1 > /dev/null
    exec_ns $POP_NS ip addr add 10.0.2.2/24 dev $POP_DL
    exec_ns $POP_NS ip addr add 10.0.3.1/24 dev $POP_UL
    exec_ns $POP_NS ip link set $POP_DL up
    exec_ns $POP_NS ip link set $POP_UL up
    # Route to H1 network via R1
    exec_ns $POP_NS ip route add 10.0.0.0/24 via 10.0.2.1
    exec_ns $POP_NS ip route add 10.0.1.0/24 via 10.0.2.1

    # --- Host 2 Configuration ---
    exec_ns $H2_NS ip addr add 10.0.3.2/24 dev $H2_DL
    exec_ns $H2_NS ip link set $H2_DL up
    exec_ns $H2_NS ip route add default via 10.0.3.1

    # 4. Apply Traffic Control (rate limiting, queuuing, etc.) 
    echo "Applying Queuing Configuration..."

    # Configure UL queue on dishy
    exec_ns $DISH_NS tc qdisc add dev $DISH_UL root handle 1: htb default 10
    exec_ns $DISH_NS tc class add dev $DISH_UL parent 1: classid 1:10 htb rate 70mbit burst 15k
    exec_ns $DISH_NS tc qdisc add dev $DISH_UL parent 1:10 handle 20: $QDISC limit 4000

    # Configure DL queue on satellite
    exec_ns $SAT_NS tc qdisc add dev $SAT_DL root handle 2: htb default 10
    exec_ns $SAT_NS tc class add dev $SAT_DL parent 2: classid 2:10 htb rate 300mbit burst 15k
    exec_ns $SAT_NS tc qdisc add dev $SAT_DL parent 2:10 handle 20: $QDISC limit 1500

    # Configure PoP queue
    # exec_ns $SAT_NS tc qdisc add dev $SAT_UL root handle 1: htb default 10
    # exec_ns $SAT_NS tc class add dev $SAT_UL parent 1: classid 1:10 htb rate 500mbit burst 15k
    if [ "$POP" = true ]; then 
        setup_pop
    fi

    echo "------------------------------------------------"
    echo "Setup Complete!"
    echo "Host 1 IP: 10.0.1.1 (Namespace: $H1_NS)"
    echo "Host 2 IP: 10.0.3.2 (Namespace: $H2_NS)"
    echo "------------------------------------------------"
    echo "To test bandwidth (requires iperf3):"
    echo "1. Start Server: sudo ip netns exec $H2_NS iperf3 -s"
    echo "2. Start Client: sudo ip netns exec $H1_NS iperf3 -c 10.0.3.2"
}


setup_pop() {
    local CLASS_FAST="10"
    local CLASS_SLOW="20"
    local MARK_SLOW="0x20"
    local LINK_SPEED="10gbit"
    local LIMIT_RATE="500mbit"

    exec_ns $POP_NS tc qdisc add dev $POP_DL root handle 3: htb default "$CLASS_FAST"
    exec_ns $POP_NS tc class add dev $POP_DL parent 3: classid 3:1 htb rate $LINK_SPEED ceil $LINK_SPEED
    exec_ns $POP_NS tc class add dev $POP_DL parent 3:1 classid 3:$CLASS_FAST htb \
        rate $LINK_SPEED ceil $LINK_SPEED
    # Never hit because LINK_SPEED is so fast
    exec_ns $POP_NS tc qdisc add dev $POP_DL parent 3:$CLASS_FAST "$QDISC_POP" 

    # Root HTB packets before dropping from head
    exec_ns $POP_NS tc class add dev $POP_DL parent 3:1 classid 3:$CLASS_SLOW htb \
        rate $LIMIT_RATE ceil $LIMIT_RATE
    exec_ns $POP_NS tc qdisc add dev $POP_DL parent 3:$CLASS_SLOW "$QDISC_POP" limit 700

    # --- C. Filters ---
    # Direct traffic based on the FW Mark set by Iptables
    exec_ns $POP_NS tc filter add dev $POP_DL protocol ip parent 3:0 prio 1 handle $MARK_SLOW fw flowid 3:$CLASS_SLOW
    # Note: No filter needed for FAST; it is the default class.

    # Apply marking logic
    exec_ns $POP_NS nft -f pop.nft
}

status() {
    # Check if namespaces exist first to avoid spamming errors
    if ! ip netns list | grep -q "$SAT_NS"; then
        echo "Error: Environment not set up. Run 'setup' first."
        exit 1
    fi

    echo "Monitoring HTB statistics. Press Ctrl+C to stop."
    
    while true; do
        clear
        echo "=== Network Status $(date +%H:%M:%S) ==="
        echo "Traffic flow: Host 1 -> [Queue 1: 500Mb] -> [Queue 2: 250Mb] -> Host 2"
        
        echo ""
        echo "--- Queue 1 (Router 1) ---"
        echo "Interface: $SAT_UL | Limit: 500 Mbits"
        # -s: stats, -d: detailed (shows drops/overlimits)
        exec_ns $SAT_NS tc -s -d qdisc show dev $SAT_UL

        echo ""
        echo "--- Queue 2 (Router 2) ---"
        echo "Interface: $POP_UL | Limit: 250 Mbits"
        exec_ns $POP_NS tc -s -d qdisc show dev $POP_UL

        # echo ""
        # echo "--- Throughput Snapshot ---"
        # # Reading raw bytes from sysfs is faster than parsing 'ip -s link'
        # H1_TX=$(exec_ns $H1_NS cat /sys/class/net/$H1_UL/statistics/tx_bytes)
        # H2_RX=$(exec_ns $H2_NS cat /sys/class/net/$H2_DL/statistics/rx_bytes)
        
        # # Convert to readable MB roughly
        # echo "Host 1 Total Sent: $(($H1_TX / 1024 / 1024)) MB"
        # echo "Host 2 Total Recv: $(($H2_RX / 1024 / 1024)) MB"

        exec_ns $SAT_NS nft list set inet traffic_shaper flow_meter

        sleep 1
    done
}

# Enable the PoP "DDos prevention" logic
QDISC="${QDISC:-pfifo_head_drop}" # or pfifo for tail drop
POP="${POP:-false}"
QDISC_POP="${QDISC_POP:-pfifo_head_drop}" # or pfifo for tail drop

# Main Argument Parsing
case "${1:-}" in
    setup)
        echo "QDISC=$QDISC"
        echo "POP=$POP"
        echo "QDISC_POPF=$QDISC_POP"
        setup
        ;;
    teardown)
        teardown
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: sudo bash $0 [setup|teardown|status]"
        exit 1
        ;;
esac


