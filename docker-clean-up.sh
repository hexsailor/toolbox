docker_clean() {                                                                                                   
    local LOG_THRESHOLD="2G"  # change this to adjust minimum log size to flag
                                                                                                                   
    echo "=== Docker Disk Usage ==="
    docker system df                                                                                               
    echo ""                                                                                                        

    # --- Log files check ---
    echo "=== Container logs over ${LOG_THRESHOLD} ==="
    local big_logs
    big_logs=$(sudo find /var/lib/docker/containers/ -name "*-json.log" -size +${LOG_THRESHOLD} 2>/dev/null)

    if [[ -z "$big_logs" ]]; then
        echo "  No large log files found."
    else
        sudo find /var/lib/docker/containers/ -name "*-json.log" -size +${LOG_THRESHOLD} \
            -exec du -h {} \; 2>/dev/null | sort -hr
        echo ""
        read "?Truncate all log files over ${LOG_THRESHOLD}? [y/N] " confirm_logs
        if [[ "$confirm_logs" == [yY] ]]; then
            echo "$big_logs" | while read -r logfile; do
                echo "  Truncating: $logfile"
                sudo truncate -s 0 "$logfile"
            done
            echo "  Logs cleared."
        else
            echo "  Skipped log cleanup."
        fi
    fi

    echo ""

    # --- Images check ---
    echo "=== Images older than 24h that will be removed ==="
    docker images --filter "until=24h" --format "  {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"
    echo ""
    read "?Remove unused images/containers older than 24h? [y/N] " confirm_images
    if [[ "$confirm_images" == [yY] ]]; then
        docker container prune -f
        docker image prune -a -f --filter "until=24h"
        echo "  Images cleaned."
    else
        echo "  Skipped image cleanup."
    fi

    echo ""
    echo "=== Final disk usage ==="
    docker system df
    df -h /
}
