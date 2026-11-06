_ZONE_COUNTRIES = {
    "europe": (
        "AD AL AM AT AZ BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GE GR HR HU IE IS IT LI LT "
        "LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SK SM TR UA VA"
    ),
    "africa": (
        "AO BF BI BJ BW CD CF CG CI CM CV DJ DZ EG ER ET GA GH GM GN GQ GW KE KM LR LS LY MA "
        "MG ML MR MU MW MZ NA NE NG RW SC SD SL SN SO SS ST SZ TD TG TN TZ UG ZA ZM ZW"
    ),
    "north_america": "BM CA GL PM US",
    "latin_america": (
        "AG AR BB BO BR BS BZ CL CO CR CU DM DO EC GD GF GT GY HN HT JM KN LC MX NI PA PE PR "
        "PY SR SV TT UY VC VE"
    ),
    "asia": (
        "AF BD BN BT CN HK ID IN JP KG KH KP KR KZ LA LK MM MN MO MV MY NP PH PK SG TH TJ TL "
        "TM TW UZ VN"
    ),
    "middle_east": "AE BH IL IQ IR JO KW LB OM PS QA SA SY YE",
    "oceania": "AU FJ FM KI MH NC NR NZ PF PG PW SB TO TV VU WS",
}

ZONES: dict[str, tuple[str, ...]] = {
    zone: tuple(countries.split()) for zone, countries in _ZONE_COUNTRIES.items()
}

COUNTRY_ZONES: dict[str, str] = {
    country: zone for zone, countries in ZONES.items() for country in countries
}


def countries_of(zone: str) -> tuple[str, ...]:
    return ZONES.get(zone, ())


def fully_covered_zones(countries: set[str]) -> list[str]:
    return [zone for zone, members in ZONES.items() if set(members) <= countries]
