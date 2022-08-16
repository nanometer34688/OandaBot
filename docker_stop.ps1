 Write-Output "Finding and deleting all docker containers with the IMAGE=oandabot_oandabot"
 docker rm $(docker stop $(docker ps -a -q --filter ancestor=oandabot_oandabot --format="{{.ID}}"))