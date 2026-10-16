SUPPORTED_CONTENT_LANGS = {"en", "fr", "sw", "yo", "ha"}

LANG_NAMES = {"fr": "French", "sw": "Swahili", "yo": "Yoruba", "ha": "Hausa"}

STRINGS = {
    "en": {
        "likely_scam": "Likely a scam — {category}",
        "weak_match": "This has some warning signs of '{category}' — be careful",
        "verify_officially": "Before acting on this message, verify it through an official channel you trust (the company's app, a number you already have saved) rather than any contact info in the message itself.",
        "pressure_headline": "No exact match, but this message uses pressure tactics",
        "pressure_advice": "Messages that push you to act 'immediately' or 'urgently' are a common scam tactic even when the specific request doesn't match a known pattern. Slow down and verify independently before responding.",
        "ai_failed_headline": "We couldn't finish the full check",
        "ai_failed_advice": "Our AI check didn't complete just now, so we can't tell you this message is safe. Try again in a moment — and until then, don't click links, share codes, or send money because of it.",
        "safe_headline": "No known scam pattern detected",
        "safe_advice": "We didn't match this against any known scam pattern, but that isn't a guarantee it's safe. If money, passwords, or personal ID details are involved, verify through an official channel first.",
        "ai_source": "TrustLine AI reasoning (not from the curated pattern list)",
        "yt_failed_headline": "Couldn't fetch that YouTube video's details",
        "yt_failed_notice": "We couldn't automatically read this video right now. Paste the video's title, description, or comment text instead and we'll check that.",
        "platform_headline": "We can't automatically read {platform} links yet",
        "platform_notice": "{platform} blocks automatic reading of posts. Copy the caption or message text from the post and paste it here instead — we'll check that.",
    },
    "fr": {
        "likely_scam": "Probablement une arnaque — {category}",
        "weak_match": "Ce message présente des signes d'alerte de « {category} » — soyez prudent",
        "verify_officially": "Avant d'agir sur ce message, vérifiez-le auprès d'un canal officiel de confiance (l'application de l'entreprise, un numéro que vous avez déjà enregistré) plutôt qu'avec les coordonnées indiquées dans le message lui-même.",
        "pressure_headline": "Aucune correspondance exacte, mais ce message utilise des tactiques de pression",
        "pressure_advice": "Les messages qui vous poussent à agir « immédiatement » ou « d'urgence » sont une tactique d'arnaque courante, même lorsque la demande ne correspond à aucun schéma connu. Prenez le temps de vérifier de façon indépendante avant de répondre.",
        "ai_failed_headline": "Nous n'avons pas pu terminer la vérification complète",
        "ai_failed_advice": "Notre vérification par IA n'a pas abouti à l'instant, nous ne pouvons donc pas vous dire que ce message est sûr. Réessayez dans un instant — et d'ici là, ne cliquez sur aucun lien, ne partagez aucun code et n'envoyez pas d'argent à cause de ce message.",
        "safe_headline": "Aucun schéma d'arnaque connu détecté",
        "safe_advice": "Nous n'avons trouvé aucune correspondance avec un schéma d'arnaque connu, mais cela ne garantit pas que le message soit sûr. Si de l'argent, des mots de passe ou des pièces d'identité sont en jeu, vérifiez d'abord par un canal officiel.",
        "ai_source": "Analyse par l'IA de TrustLine (hors de la bibliothèque de schémas)",
        "yt_failed_headline": "Impossible de récupérer les détails de cette vidéo YouTube",
        "yt_failed_notice": "Nous n'avons pas pu lire cette vidéo automatiquement pour le moment. Collez plutôt le titre, la description ou le texte des commentaires de la vidéo et nous vérifierons cela.",
        "platform_headline": "Nous ne pouvons pas encore lire automatiquement les liens {platform}",
        "platform_notice": "{platform} bloque la lecture automatique des publications. Copiez la légende ou le texte du message de la publication et collez-le ici — nous vérifierons cela.",
    },
    "sw": {
        "likely_scam": "Huenda ni ulaghai — {category}",
        "weak_match": "Ujumbe huu una dalili za tahadhari za '{category}' — kuwa mwangalifu",
        "verify_officially": "Kabla ya kuchukua hatua kuhusu ujumbe huu, uthibitishe kupitia njia rasmi unayoiamini (programu ya kampuni, nambari uliyoihifadhi tayari) badala ya maelezo ya mawasiliano yaliyo kwenye ujumbe wenyewe.",
        "pressure_headline": "Hakuna mfanano kamili, lakini ujumbe huu unatumia mbinu za kushinikiza",
        "pressure_advice": "Ujumbe unaokushinikiza kuchukua hatua 'mara moja' au 'kwa dharura' ni mbinu ya kawaida ya ulaghai hata kama ombi lenyewe halilingani na mtindo unaojulikana. Punguza kasi na uthibitishe kwa njia huru kabla ya kujibu.",
        "ai_failed_headline": "Hatukuweza kukamilisha ukaguzi kamili",
        "ai_failed_advice": "Ukaguzi wetu wa AI haukukamilika sasa hivi, kwa hivyo hatuwezi kukuambia ujumbe huu ni salama. Jaribu tena baada ya muda mfupi — na hadi hapo, usibofye viungo, usishiriki nambari za siri wala usitume pesa kwa sababu yake.",
        "safe_headline": "Hakuna mtindo wa ulaghai unaojulikana uliogunduliwa",
        "safe_advice": "Hatukupata mfanano wowote na mtindo wa ulaghai unaojulikana, lakini hilo si uhakika kuwa ni salama. Ikiwa pesa, nenosiri au taarifa za kitambulisho zinahusika, thibitisha kwanza kupitia njia rasmi.",
        "ai_source": "Uchambuzi wa AI wa TrustLine (si kutoka orodha ya mitindo iliyoratibiwa)",
        "yt_failed_headline": "Imeshindwa kupata maelezo ya video hiyo ya YouTube",
        "yt_failed_notice": "Hatukuweza kusoma video hii kiotomatiki kwa sasa. Bandika kichwa, maelezo au maandishi ya maoni ya video badala yake nasi tutayakagua.",
        "platform_headline": "Bado hatuwezi kusoma viungo vya {platform} kiotomatiki",
        "platform_notice": "{platform} huzuia usomaji wa kiotomatiki wa machapisho. Nakili maelezo mafupi au maandishi ya ujumbe kutoka kwenye chapisho na uyabandike hapa badala yake — tutayakagua.",
    },
    "yo": {
        "likely_scam": "Ó ṣeé ṣe kó jẹ́ ìjìbìtì — {category}",
        "weak_match": "Ìfiránṣẹ́ yìí ní àwọn àmì ìkìlọ̀ ti '{category}' — ṣọ́ra",
        "verify_officially": "Kí o tó ṣe ohunkóhun lórí ìfiránṣẹ́ yìí, jẹ́rìísí rẹ̀ nípasẹ̀ ọ̀nà òtítọ́ tí o gbẹ́kẹ̀lé (áàpù ilé-iṣẹ́ náà, nọ́ńbà tí o ti fi pamọ́ tẹ́lẹ̀) dípò àlàyé ìbánisọ̀rọ̀ tó wà nínú ìfiránṣẹ́ fúnra rẹ̀.",
        "pressure_headline": "Kò sí ìbáramu pàtó, ṣùgbọ́n ìfiránṣẹ́ yìí ń lo ọgbọ́n ìfipámúni",
        "pressure_advice": "Àwọn ìfiránṣẹ́ tó ń ta ọ́ láti ṣe nǹkan 'lẹ́sẹ̀kẹsẹ̀' tàbí 'ní kánmọ́' jẹ́ ọgbọ́n ìjìbìtì tó wọ́pọ̀ kódà bí ìbéèrè pàtó náà kò bá bá àpẹẹrẹ tí a mọ̀ mu. Dín kù, kí o sì jẹ́rìísí lọ́nà tirẹ̀ kí o tó dáhùn.",
        "ai_failed_headline": "A kò lè parí àyẹ̀wò kíkún náà",
        "ai_failed_advice": "Àyẹ̀wò AI wa kò parí ní ìsinsìnyí, nítorí náà a kò lè sọ fún ọ pé ìfiránṣẹ́ yìí wà ní ààbò. Gbìyànjú lẹ́ẹ̀kan sí i láìpẹ́ — àti títí dìgbà náà, má ṣe tẹ ọ̀nà àsopọ̀, má ṣe pín kóòdù, tàbí fi owó ránṣẹ́ nítorí rẹ̀.",
        "safe_headline": "A kò rí àpẹẹrẹ ìjìbìtì tí a mọ̀",
        "safe_advice": "A kò rí ìbáramu pẹ̀lú àpẹẹrẹ ìjìbìtì kankan tí a mọ̀, ṣùgbọ́n ìyẹn kì í ṣe ìdánilójú pé ó wà ní ààbò. Bí owó, ọ̀rọ̀ìpamọ́ tàbí àlàyé ìdánimọ̀ bá ní í ṣe pẹ̀lú rẹ̀, jẹ́rìísí nípasẹ̀ ọ̀nà òtítọ́ lákọ̀ọ́kọ́.",
        "ai_source": "Àyẹ̀wò AI ti TrustLine (kì í ṣe láti inú àtòjọ àpẹẹrẹ tí a ṣàkójọ)",
        "yt_failed_headline": "A kò lè gba àlàyé fídíò YouTube náà",
        "yt_failed_notice": "A kò lè ka fídíò yìí fúnra wa ní ìsinsìnyí. Lẹ̀ àkọlé, àpèjúwe tàbí ọ̀rọ̀ ìwòye fídíò náà dípò rẹ̀, a ó sì ṣàyẹ̀wò rẹ̀.",
        "platform_headline": "A kò tíì lè ka àwọn ọ̀nà àsopọ̀ {platform} fúnra wa",
        "platform_notice": "{platform} dí kíkà àwọn ìfiránṣẹ́ fúnra ẹ̀rọ. Ṣe ẹ̀dà àkọlé tàbí ọ̀rọ̀ ìfiránṣẹ́ láti inú ìfiránṣẹ́ náà kí o sì lẹ̀ ẹ́ síbí dípò rẹ̀ — a ó ṣàyẹ̀wò rẹ̀.",
    },
    "ha": {
        "likely_scam": "Wataƙila zamba ce — {category}",
        "weak_match": "Wannan saƙon yana da alamun gargaɗi na '{category}' — ka yi hankali",
        "verify_officially": "Kafin ka ɗauki mataki kan wannan saƙon, ka tabbatar da shi ta hanyar hukuma da ka amince da ita (manhajar kamfanin, lambar da ka riga ka adana) maimakon bayanan sadarwa da ke cikin saƙon kansa.",
        "pressure_headline": "Babu cikakken daidaituwa, amma wannan saƙon yana amfani da dabarun matsa lamba",
        "pressure_advice": "Saƙonnin da ke matsa maka ka yi aiki 'nan da nan' ko 'cikin gaggawa' dabarar zamba ce da aka saba ko da takamaiman buƙatar ba ta dace da wani sanannen tsari ba. Ka ragu, ka tabbatar da kanka kafin ka amsa.",
        "ai_failed_headline": "Ba mu iya kammala cikakken bincike ba",
        "ai_failed_advice": "Binciken AI ɗinmu bai kammala ba a yanzu, don haka ba za mu iya gaya maka wannan saƙon lafiya yake ba. Ka sake gwadawa nan gaba kaɗan — kuma har lokacin, kada ka taɓa hanyoyin haɗi, kada ka raba lambobi, ko ka aika kuɗi saboda shi.",
        "safe_headline": "Ba a gano wani sanannen tsarin zamba ba",
        "safe_advice": "Ba mu sami wata daidaituwa da sanannen tsarin zamba ba, amma hakan ba tabbaci ba ne cewa lafiya yake. Idan kuɗi, kalmomin sirri ko bayanan shaida na cikin lamarin, ka fara tabbatarwa ta hanyar hukuma.",
        "ai_source": "Nazarin AI na TrustLine (ba daga jerin tsare-tsaren da aka tattara ba)",
        "yt_failed_headline": "Ba a iya samo bayanan bidiyon YouTube ɗin ba",
        "yt_failed_notice": "Ba mu iya karanta wannan bidiyon ta atomatik a yanzu ba. Ka liƙa taken bidiyon, bayaninsa, ko rubutun sharhi maimakon haka za mu duba shi.",
        "platform_headline": "Har yanzu ba za mu iya karanta hanyoyin haɗi na {platform} ta atomatik ba",
        "platform_notice": "{platform} yana hana karanta rubuce-rubuce ta atomatik. Ka kwafi taken hoto ko rubutun saƙon daga rubutun ka liƙa a nan maimakon haka — za mu duba shi.",
    },
}


def normalize_lang(lang: str | None) -> str:
    """Only languages we have full verdict content for are honored; anything else (e.g. the
    UI-only Pidgin option) gets English content."""
    return lang if lang in SUPPORTED_CONTENT_LANGS else "en"


def t(lang: str, key: str, **kwargs) -> str:
    return STRINGS[lang][key].format(**kwargs)
