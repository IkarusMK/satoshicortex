# tools

Not an afterthought folder — three of these are build parts, and the rest make
the shipped data reproducible.

| | What it does | Used by |
|---|---|---|
| `geo_bauen.py` | Builds the compact geo lookup that ships inside the image | `app/Dockerfile` |
| `i18n_pruefen.py` | Checks that both languages are complete and no key is orphaned | CI (`check.yml`) |
| `onion_stapeltest.sh` | Exercises the onion service lifecycle against a real Tor | CI (`check.yml`) |
| `karte_bauen.py` | Builds the world map SVG from Natural Earth outlines | run by hand |
| `regionen_bauen.py` | Builds the per-country region maps from the same source | run by hand |
| `regionen_zuordnen.py` | Maps the IP database's region names onto those outlines | run by hand |
| `quellen_pruefen.py` | Measures whether the shipped news sources answer over Tor | run by hand |
| `pruefen.sh` | Runs the whole local check the way CI does | run by hand |

The last five are not needed to run a node. They are here so that the data
shipped in `app/data/` and `assets/` can be rebuilt from its sources instead of
having to be taken on trust.
