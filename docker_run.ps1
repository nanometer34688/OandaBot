$pairs = @("GBP_USD", "GBP_JPY", "GBP_AUD", "GBP_CAD", "GBP_NZD","EUR_GBP")
$i=0
for(;$i -le $pairs.Length; $i++)
{
    $name=$pairs[$i]
    Write-Output "Running OANDA BOT with STRATEGY 2 against $name"
    docker run -d -v $pwd\trades:/home/OandaBot/trades --name oandabot_$name oandabot_oandabot python3 main.py -t -i $pairs[$i]
}
