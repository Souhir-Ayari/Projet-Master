# Notes retirées de l'état de l'art, à réutiliser dans la synthèse critique

## 2.1 CTINexus : construction de graphes de connaissances CTI par apprentissage en contexte
CTINexus montre qu'un LLM peut extraire des connaissances structurées d'un texte de sécurité sans réentraînement, ce que nous reprenons pour l'extraction des attaques et des défenses à partir d'articles. Il illustre aussi l'intérêt de passer par des entités avant d'aller vers une représentation plus riche. En revanche, son absence de défense produite et de rattachement à une taxonomie motive deux choix de notre approche : produire une recommandation de défense et ancrer chaque cas dans MITRE ATLAS.

## 2.2 LADDER : extraction de schémas d'attaque reliés à MITRE ATT&CK
LADDER confirme qu'il est préférable de raisonner sur le mécanisme d'une attaque plutôt que sur des indicateurs isolés ; c'est l'idée que nous poussons plus loin en décrivant chaque attaque par une chaîne causale. Son rattachement des schémas d'attaque à une taxonomie est également un principe que nous reprenons. La différence tient au choix de la taxonomie : les attaques que nous étudions visent des LLM, ce qui nous conduit à utiliser MITRE ATLAS plutôt qu'ATT&CK.

## 2.3 FALCON : génération de règles de détection à partir de la CTI
FALCON montre qu'il est possible de passer de la CTI à une défense concrète, ce qui correspond à l'objectif de notre travail. Il en révèle aussi le point faible : lorsque la vérification dépend du modèle générateur, elle hérite de ses biais. Cette limite motive l'un de nos choix principaux, qui consiste à séparer la vérification de la génération et à la confier à une règle déterministe, extérieure au LLM.

## 2.4 TechniqueRAG : classification des techniques d'attaque par génération augmentée
TechniqueRAG valide une idée que nous reprenons : restreindre les techniques proposées au modèle à une liste de candidats et vérifier l'identifiant produit, plutôt que de laisser le modèle choisir librement. Notre approche applique ce principe à MITRE ATLAS. La lacune qu'il laisse ouverte, l'effet d'une erreur de classification sur la suite du traitement, est précisément l'une des questions que nous étudions dans l'évaluation.

## 2.5 ATAG : graphes d'attaque et base de vulnérabilités des LLM
ATAG est le travail le plus proche du nôtre par la nature de ses données. Il confirme l'intérêt d'une base de cas ancrée dans MITRE ATLAS et issue de la littérature. Notre approche se distingue en construisant cette base automatiquement, puis en mesurant ce que cette automatisation coûte par rapport à une base relue à la main, une question que la construction manuelle de la LVD ne permet pas de poser.

## 2.6 Self-Refine : amélioration itérative par auto-évaluation
Self-Refine apporte l'idée d'un cycle « proposer, vérifier, réviser », que nous reprenons pour la production des recommandations. Ses limites justifient toutefois une différence essentielle : dans notre approche, l'étape de vérification n'est pas confiée au modèle qui a produit la recommandation, mais à une règle déterministe. Self-Refine sert également de point de comparaison dans notre évaluation, afin de mesurer ce que l'auto-vérification par le même modèle garantit réellement.
