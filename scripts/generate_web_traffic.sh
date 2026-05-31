#!/bin/bash
#
# generate_web_traffic.sh
# Workload script to simulate web traffic to top 500 websites.
# Workload script to simulate web traffic to top 550 websites.
# Performs DNS lookups first, then staggers HTTP requests with up to 500ms delay.

WEBSITES=(
  "google.com" "youtube.com" "facebook.com" "twitter.com" "instagram.com" "linkedin.com" "apple.com" "microsoft.com" "netflix.com" "amazon.com"
  "wikipedia.org" "yahoo.com" "reddit.com" "ebay.com" "bing.com" "live.com" "office.com" "twitch.tv" "pinterest.com" "github.com"
  "stackoverflow.com" "zoom.us" "imdb.com" "craigslist.org" "zillow.com" "yelp.com" "etsy.com" "dropbox.com" "slack.com" "chase.com"
  "wellsfargo.com" "bankofamerica.com" "capitalone.com" "americanexpress.com" "paypal.com" "stripe.com" "squareup.com" "intuit.com" "hulu.com" "disneyplus.com"
  "hbo.com" "spotify.com" "pandora.com" "soundcloud.com" "nytimes.com" "wsj.com" "washingtonpost.com" "cnn.com" "foxnews.com" "nbcnews.com"
  "usatoday.com" "npr.org" "bbc.com" "theguardian.com" "ft.com" "telegraph.co.uk" "independent.co.uk" "sky.com" "rightmove.co.uk" "ebay.co.uk"
  "deliveroo.co.uk" "asos.com" "argos.co.uk" "tesco.com" "sainsburys.co.uk" "google.fr" "amazon.fr" "leboncoin.fr" "orange.fr" "google.de"
  "amazon.de" "bild.de" "spiegel.de" "ebay.de" "web.de" "t-online.de" "gmx.net" "google.it" "amazon.it" "corriere.it"
  "repubblica.it" "google.es" "amazon.es" "marca.com" "elmundo.es" "elpais.com" "booking.com" "ikea.com" "zalando.com" "revolut.com"
  "klarna.com" "vinted.com" "bbc.co.uk" "gov.uk" "apple.co.uk" "yahoo.co.uk" "live.co.uk" "msn.co.uk" "bing.co.uk" "paypal.co.uk"
  "gumtree.com" "autotrader.co.uk" "moneysavingexpert.com" "halfords.com" "just-eat.co.uk" "dominos.co.uk" "pizzahut.co.uk" "kfc.co.uk" "mcdonalds.co.uk" "nandos.co.uk"
  "burgerking.co.uk" "subway.co.uk" "costa.co.uk" "greggs.co.uk" "pret.co.uk" "wetherspoon.co.uk" "ocado.com" "caffenero.com" "starbucks.co.uk" "aldi.co.uk"
  "morrisons.com" "asda.com" "lidl.co.uk" "waitrose.com" "coop.co.uk" "iceland.co.uk" "marksandspencer.com" "johnlewis.com" "boots.com" "next.co.uk"
  "matalan.co.uk" "riverisland.com" "newlook.com" "topshop.com" "boohoo.com" "missguided.co.uk" "prettylittlething.com" "shein.co.uk" "hollisterco.com" "zara.com"
  "hm.com" "primark.com" "tkmaxx.com" "urbanoutfitters.com" "abercrombie.com" "superdry.com" "jdsports.co.uk" "sportsdirect.com" "footasylum.com" "schuh.co.uk"
  "size.co.uk" "office.co.uk" "clarksshoes.com" "footlocker.co.uk" "vans.co.uk" "converse.com" "nike.com" "adidas.com" "puma.com" "reebok.com"
  "underarmour.co.uk" "newbalance.co.uk" "asics.co.uk" "skechers.com" "timberland.co.uk" "drmartens.com" "clarks.co.uk" "ugg.com" "thebodyshop.com" "superdrug.com"
  "lush.com" "feelunique.com" "cultbeauty.co.uk" "lookfantastic.com" "spacenk.com" "charlottetilbury.com" "macys.com" "nordstrom.com" "jcpenney.com" "bloomingdales.com"
  "saksfifthavenue.com" "neimanmarcus.com" "bergdorfgoodman.com" "barneys.com" "dillards.com" "lordandtaylor.com" "kohls.com" "sears.com" "belk.com" "target.com"
  "walmart.com" "costco.com" "samsclub.com" "bjs.com" "kroger.com" "publix.com" "safeway.com" "albertsons.com" "vons.com" "jewelosco.com"
  "acmemarkets.com" "shaws.com" "tomthumb.com" "randalls.com" "pavilions.com" "starmarket.com" "carrsqc.com" "heb.com" "ralphs.com" "smithsfoodanddrug.com"
  "kingsoopers.com" "frysfood.com" "qfc.com" "citymarket.com" "dillons.com" "bakersplus.com" "gerbes.com" "food4less.com" "foodsco.net" "fredmeyer.com"
  "harristeeter.com" "marianos.com" "metro.ca" "loblaws.ca" "sobeys.com" "nofrills.ca" "realcanadiansuperstore.ca" "freshco.ca" "independentcitymarket.ca" "valumart.ca"
  "zehrs.ca" "fortinos.ca" "extrafoods.ca" "provigo.ca" "maxi.ca" "saveonfoods.com" "urbanfare.com" "price-smart.ca" "coopersfoods.com" "owenfood.com"
  "koodomobile.com" "fido.ca" "virginmobile.ca" "chatrwireless.com" "publicmobile.ca" "luckymobile.ca" "freedommobile.ca" "windmobile.ca" "mobilicity.ca" "shaw.ca"
  "telus.com" "bell.ca" "rogers.com" "videotron.com" "cogeco.ca" "sasktel.com" "mts.ca" "eastlink.ca" "xplornet.com" "teksavvy.com"
  "att.com" "verizon.com" "t-mobile.com" "sprint.com" "uscellular.com" "cricketwireless.com" "boostmobile.com" "metropcs.com" "straighttalk.com" "tracfone.com"
  "net10.com" "simplemobile.com" "familymobile.com" "pagepluscellular.com" "totalwireless.com" "ting.com" "republicwireless.com" "consumercellular.com" "projectfi.com" "mintmobile.com"
  "ultramobile.com" "lycamobile.com" "h2owirelessnow.com" "ptel.com" "rokstarmobile.com" "good2gomobile.com" "selectelwireless.com" "airvoicewireless.com" "expo-mobile.com" "goredpocket.com"
  "blackwireless.com" "spotmobile.com" "joltmobile.com" "chit-chatmobile.com" "enviromobile.com" "att.co.uk" "verizon.co.uk" "t-mobile.co.uk" "vodafone.co.uk" "o2.co.uk"
  "ee.co.uk" "three.co.uk" "giffgaff.com" "tescomobile.com" "virginmedia.com" "bt.com" "talkmobile.co.uk" "talktalk.co.uk" "plus.net" "nowtv.com"
  "postoffice.co.uk" "lebara.com" "smartymobile.co.uk" "lebara.co.uk" "lycamobile.co.uk" "smarty.co.uk" "idmobile.co.uk" "voxi.co.uk" "plusnet.co.uk" "utilitywarehouse.co.uk"
  "zen.co.uk" "kcom.com" "hyperoptic.com" "gigaclear.com" "communityfibre.co.uk" "cityfibre.com" "truespeed.com" "wightfibre.com" "toob.co.uk" "b4rn.co.uk"
  "zzoomm.com" "jurassicfibre.com" "brsk.co.uk" "fraw.co.uk" "countyband.co.uk" "airband.co.uk" "voneus.com" "swishfibre.com" "netomnia.com" "msn.fr"
  "yahoo.fr" "bing.fr" "live.fr" "free.fr" "sfr.fr" "bouyguestelecom.fr" "laposte.fr" "pagesjaunes.fr" "cdiscount.com" "fnac.com"
  "darty.com" "boulanger.com" "auchan.fr" "carrefour.fr" "leclerc.fr" "intermarche.com" "systeme-u.fr" "casino.fr" "cora.fr" "monoprix.fr"
  "franprix.fr" "picard.fr" "laredoute.fr" "kiabi.fr" "promod.fr" "camaieu.fr" "nafnaf.fr" "jules.fr" "pimkie.fr" "etam.fr"
  "zara.fr" "hm.fr" "mango.fr" "bershka.fr" "stradivarius.fr" "pullandbear.fr" "oysho.fr" "massimodutti.fr" "galerieslafayette.com" "printemps.com"
  "lebonmarche.fr" "bhv.fr" "samaritaine.fr" "sephora.fr" "marionnaud.fr" "nocibe.fr" "yves-rocher.fr" "douglas.de" "rossmann.de" "flaconi.de"
  "parfumdreams.de" "notino.de" "pieper.de" "muller.de" "dm.de" "budni.de" "edeka.de" "rewe.de" "kaufland.de" "real.de"
  "netto.de" "penny.de" "aldi-nord.de" "aldi-sued.de" "lidl.de" "norma.de" "otto.de" "tchibo.de" "baur.de" "klingel.de"
  "schwab.de" "heine.de" "witt-weiden.de" "bader.de" "mona.de" "kik.de" "c-and-a.com" "galeria-kaufhof.de" "karstadt.de" "breuninger.com"
  "kadewe.de" "peek-cloppenburg.de" "engelhorn.de" "fashionid.de" "aboutyou.de" "mirapodo.de" "brille24.de" "misterspex.de" "fielmann.de" "apollo.de"
  "alibaba.com" "jd.com" "wechat.com" "sina.com.cn" "sohu.com" "xinhuanet.com" "toutiao.com" "bilibili.com" "youku.com" "iqiyi.com"
  "vimeo.com" "dailymotion.com" "hulu.com" "disneyplus.com" "peacocktv.com" "paramountplus.com" "crunchyroll.com" "funimation.com" "tubitv.com" "plutotv.com"
  "spotify.com" "soundcloud.com" "pandora.com" "iheart.com" "tidal.com" "deezer.com" "napster.com" "qobuz.com" "mixcloud.com" "bandcamp.com"
  "steampowered.com" "epicgames.com" "ea.com" "origin.com" "ubisoft.com" "blizzard.com" "rockstargames.com" "bethesda.net" "riotgames.com" "nintendo.com"
  "playstation.com" "xbox.com" "roblox.com" "minecraft.net" "gog.com" "humblebundle.com" "itch.io" "greenmangaming.com" "fanatical.com" "gamersgate.com"
  "expedia.com" "kayak.com" "orbitz.com" "travelocity.com" "priceline.com" "hotwire.com" "cheapflights.com" "agoda.com" "tripadvisor.com" "trivago.com"
  "hotels.com" "hostelworld.com" "airbnb.com" "vrbo.com" "homeaway.com" "skyscanner.com" "momondo.com" "kiwi.com" "hopper.com" "rome2rio.com"
  "google.ie" "rte.ie" "irishtimes.com" "independent.ie" "thejournal.ie" "joe.ie" "breakingnews.ie" "donedeal.ie" "daft.ie" "adverts.ie"
  "myhome.ie" "boards.ie" "gov.ie" "revenue.ie" "citizensinformation.ie" "hse.ie" "aerlingus.com" "ryanair.com" "irishrail.ie" "buseireann.ie"
  "dublinbus.ie" "bankofireland.com" "aib.ie" "ptsb.ie" "ulsterbank.ie" "creditunion.ie" "anpost.com" "supervalu.ie" "dunnesstores.com" "tesco.ie"
  "aldi.ie" "lidl.ie" "argos.ie" "harveynorman.ie" "currys.ie" "woodies.ie" "eir.ie" "vodafone.ie" "three.ie" "virginmedia.ie"
  "sky.ie" "electricireland.ie" "bordgaisenergy.ie" "sseairtricity.com" "energia.ie" "water.ie" "ticketmaster.ie" "lifestylesports.com" "elverys.ie" "brownthomas.com"
)

echo "=========================================================="
echo " Generating Web Traffic (Staggered with DNS Resolution)"
echo "=========================================================="
for site in "${WEBSITES[@]}"; do
  # Generate a random delay between 1 and 500 ms
  DELAY=$(printf "0.%03d" $(( (RANDOM % 500) + 1 )))
  
  echo "[*] Waiting ${DELAY}s..."
  sleep "$DELAY"

  echo -n "[*] Resolving ${site}... "
  # Try dig first for cleaner output, fallback to getent if dig is missing
  if command -v dig &> /dev/null; then
    dig +short "$site" | grep -E '^[0-9.]+$' | head -n 1 || echo "No IPv4 found"
  else
    getent hosts "$site" | awk '{ print $1 }' | head -n 1 || echo "Failed to resolve"
  fi

  echo -n "[*] Fetching https://${site} ... "
  
  # -L follows redirects, -s silences progress, -w prints HTTP status, -o discards body
  # --max-time ensures we don't hang indefinitely on a slow or unresponsive site
  curl -L -s -o /dev/null -w "HTTP Status: %{http_code}\n" --max-time 5 "https://${site}" || echo "Connection Failed"
done

echo -e "\nWorkload generation complete!"