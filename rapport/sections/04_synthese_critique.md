# Chapitre 3 — Synthèse critique, positionnement et contributions

Le chapitre précédent a présenté six approches, chacune avec ses propres objectifs, données et méthodes. Ce chapitre ne les compare pas entre elles : il les confronte à ce que notre approche, CARL (*Case-based Attack Remediation for LLMs*), cherche à réaliser, c'est-à-dire produire, à partir de la littérature scientifique, des recommandations de défense vérifiables contre les attaques visant les LLM. Cette comparaison permet d'identifier ce que l'état de l'art fournit déjà à CARL, ce qui lui manque, puis d'en déduire notre positionnement et nos contributions. CARL est présenté ici dans ses grandes lignes ; sa méthodologie et son architecture sont détaillées au chapitre 4. Les jugements portés sur les six approches relèvent de notre analyse des articles ; lorsqu'une propriété n'est pas décrite dans un article, nous l'indiquons comme non rapportée.

## 3.1 Critères de comparaison

Les critères de comparaison sont définis à partir de ce que CARL doit accomplir pour répondre à la problématique. Chacun correspond à une exigence de notre approche, et permet de vérifier si une approche existante la satisfait déjà :

- **la source et les attaques visées** : CARL exploite des articles scientifiques consacrés aux attaques contre les LLM ; d'où l'approche tire-t-elle ses connaissances, et quelles attaques couvre-t-elle ?
- **le mode de construction** : CARL construit sa base automatiquement ; l'approche est-elle automatique ou manuelle ?
- **la granularité** : CARL décrit chaque attaque par une chaîne causale ; à quel niveau de détail l'approche décrit-elle les attaques ?
- **la taxonomie de référence** : CARL ancre chaque attaque dans MITRE ATLAS ; à quel référentiel l'approche se rattache-t-elle ?
- **la défense et son contrôle** : CARL recommande une mesure adaptée et la vérifie hors du modèle générateur ; l'approche propose-t-elle une défense, et qui la contrôle ?
- **la traçabilité et la propagation des erreurs** : chaque réponse de CARL cite sa source, et CARL mesure l'effet d'une erreur d'une étape sur les suivantes ; l'approche permet-elle l'un et l'autre ?

## 3.2 Comparaison des approches avec CARL

Le tableau 3.1 situe les six approches par rapport à CARL selon ces critères. La dernière colonne indique ce que réalise CARL, et la dernière ligne la limite principale de chaque approche, y compris celle de CARL.

*Tableau 3.1 — Comparaison des approches de l'état de l'art avec CARL (notre analyse ; n.r. : non rapporté)*

| Critère | CTINexus | LADDER | FALCON | TechniqueRAG | ATAG | Self-Refine | **CARL (notre approche)** |
|---|---|---|---|---|---|---|---|
| Source et attaques visées | Rapports CTI ; menaces classiques | Rapports CTI ; menaces classiques | CTI ; réseau et système | Textes CTI ; menaces classiques | Articles ; agents LLM | Non spécifique | **Articles scientifiques ; attaques contre les LLM** |
| Construction | Automatique (LLM) | Automatique (BERT) | Automatique (LLM) | Automatique (RAG) | Manuelle | — | **Automatique (GLiNER, Mistral-7B)** |
| Granularité | Entités et relations | Schémas d'attaque | Règle de détection | Technique | Vulnérabilité et procédure | — | **Chaîne causale** |
| Taxonomie | Ontologie au choix | ATT&CK | n.r. | ATT&CK | ATLAS | — | **ATLAS, identifiant validé** |
| Défense et contrôle | Aucune défense | Aucune défense | Règles Snort, YARA ; contrôle en partie par le modèle | Aucune défense | Aucune défense ; évaluation des risques | Révision par le même modèle | **Mesure adaptée ou « null » ; règle hors du LLM** |
| Traçabilité et propagation | n.r. ; non mesurée | n.r. ; non mesurée | n.r. ; non mesurée | n.r. ; non mesurée | Articles sources ; non mesurée | Non ; non mesurée | **Cas, technique et article cités ; propagation mesurée** |
| Limite principale | Aucune défense | ATT&CK hors LLM | Validée par le même modèle | Effet d'une erreur non mesuré | Construction manuelle | Biais d'auto-évaluation | **Classification encore faible (chapitre 5)** |

Ce tableau montre d'abord qu'aucune approche ne couvre à elle seule l'ensemble des exigences de CARL. Chacune en satisfait une partie : la plupart construisent leurs connaissances automatiquement, ATAG partage le choix de la littérature et de MITRE ATLAS, FALCON produit une défense et Self-Refine révise ses réponses. Mais ces points forts sont dispersés entre des travaux différents, conçus pour des objectifs différents, et le plus souvent pour des menaces informatiques classiques plutôt que pour les attaques contre les LLM.

Le tableau fait ensuite apparaître une rupture nette entre la partie haute et la partie basse. Les premières lignes, qui portent sur l'extraction et l'organisation des connaissances, sont relativement bien couvertes par l'état de l'art. Les dernières, qui portent sur ce qui se passe après, c'est-à-dire produire une défense, la contrôler sans dépendre du modèle et pouvoir en retrouver la source, le sont très peu. Plus on avance vers la recommandation finale, moins les approches existantes apportent de garanties. C'est précisément sur cette partie de la chaîne que CARL concentre ses choix.

Enfin, aucune des six approches ne mesure ce que devient une erreur lorsqu'elle passe d'une étape à la suivante, alors que toutes enchaînent plusieurs traitements. La colonne de CARL n'est pas pour autant présentée comme idéale : sa dernière ligne rappelle que la classification des attaques reste son étape la plus fragile. Nous l'indiquons dès maintenant, car c'est justement la mesure de cette faiblesse et de ses effets sur les étapes suivantes qui constitue l'une de nos contributions.

## 3.3 Limites de l'état de l'art

Cette comparaison fait apparaître cinq limites de l'état de l'art par rapport à ce que vise CARL. Elles correspondent aux difficultés posées dans la problématique.

### L1 — Des connaissances tirées de rapports CTI plutôt que de la littérature scientifique

Quatre des six approches exploitent des rapports CTI, qui décrivent des incidents ou des campagnes observés. Ces rapports sont précieux pour les menaces informatiques classiques, mais les attaques contre les LLM sont aujourd'hui surtout décrites dans des articles de recherche, qui présentent à la fois le mécanisme de l'attaque et, souvent, une défense évaluée. Seul ATAG s'appuie sur des articles, et il le fait manuellement.

### L2 — Une taxonomie inadaptée aux attaques contre les LLM

LADDER et TechniqueRAG rattachent les attaques à MITRE ATT&CK, qui ne couvre pas nativement l'injection de *prompt* ou le *jailbreak*. Seul ATAG utilise MITRE ATLAS, le référentiel dédié aux systèmes d'IA. Par ailleurs, les approches qui valident un identifiant vérifient qu'il appartient à la taxonomie, ce qui n'établit pas qu'il s'agit de la bonne technique ; TechniqueRAG obtient d'ailleurs des résultats nettement plus faibles sur les descriptions les moins standardisées.

### L3 — Une granularité limitée aux entités ou aux techniques

Les approches décrivent les attaques sous la forme d'entités et de relations (CTINexus), de schémas rattachés à une technique (LADDER, TechniqueRAG) ou de règles de détection (FALCON). Aucune ne décrit explicitement le déroulement de l'attaque en étapes successives, depuis le canal d'entrée jusqu'à son effet. Or c'est ce niveau de détail qui permet de choisir une défense agissant sur un point précis de l'attaque.

### L4 — Peu de défenses, et une vérification confiée au modèle

Une seule approche produit une défense, et sa qualité est contrôlée en partie par le modèle qui l'a générée. Les travaux sur l'auto-correction montrent que ce type de vérification est fragile, car un LLM tend à valider ses propres productions (Xu et al., 2024 ; Kamoi et al., 2024). Par ailleurs, aucune approche ne prévoit explicitement le cas où la littérature ne propose pas de défense : rien n'empêche alors le modèle d'en inventer une.

### L5 — Une traçabilité rarement assurée et des erreurs évaluées étape par étape

Hormis ATAG, dont les enregistrements proviennent d'articles identifiés, les approches ne permettent pas de retrouver la source précise sur laquelle repose chaque résultat. Surtout, toutes évaluent leurs étapes isolément : la qualité d'une classification, d'une extraction ou d'une règle. Aucune ne mesure ce que devient une erreur lorsqu'elle est réutilisée par l'étape suivante, alors que, dans un système qui enchaîne extraction, classification, recherche et génération, c'est cette propagation qui détermine la qualité de la recommandation finale. ATAG, en construisant sa base à la main, évite le coût de l'automatisation sans le mesurer.

## 3.4 Positionnement

Notre positionnement découle directement des cinq limites L1 à L5. L'état de l'art a construit des composants solides : extraire des connaissances, classer une attaque, constituer une base de vulnérabilités, produire une défense ou corriger une réponse. Notre objectif n'est pas de dépasser chacun de ces composants sur sa propre tâche, mais de les réunir dans une même approche de recommandation de défenses pour les attaques visant les LLM, puis de mesurer ce qui se passe de bout en bout lorsqu'ils sont enchaînés.

CARL aborde pour cela la recommandation de défense comme un problème de raisonnement à partir de cas. Plutôt que de laisser un modèle générer librement une défense, il lui fournit des cas d'attaques documentés, extraits de la littérature et ancrés dans MITRE ATLAS ; face à une nouvelle attaque, il retrouve les cas les plus proches, adapte leur défense, puis vérifie la recommandation avant de la proposer.

Le tableau 3.2 fait le lien entre l'analyse de la section 3.3 et la conception de CARL : chaque ligne reprend l'une des cinq limites identifiées et indique le choix de conception par lequel CARL y répond.

*Tableau 3.2 — Réponse de CARL aux limites de l'état de l'art (section 3.3)*

| Limite (section 3.3) | Choix de conception de CARL |
|---|---|
| L1 — Connaissances tirées de rapports CTI, pas de la littérature | Base de cas extraite automatiquement d'articles scientifiques sur les attaques contre les LLM |
| L2 — Taxonomie inadaptée aux attaques contre les LLM | Ancrage de chaque cas dans MITRE ATLAS, avec vérification de l'identifiant proposé |
| L3 — Granularité limitée aux entités ou aux techniques | Description de chaque attaque par une chaîne causale : canal d'entrée → contournement → impact |
| L4 — Peu de défenses, vérification confiée au modèle | Recommandation par raisonnement à partir de cas, adaptée au maillon de l'attaque qu'elle casse ; « null » explicite quand aucune défense n'est documentée ; vérification par une règle déterministe, hors du LLM |
| L5 — Traçabilité rare, erreurs évaluées étape par étape | Chaque recommandation cite son cas, sa technique et son article ; évaluation de chaque étape sur les mêmes cas et mesure de la propagation des erreurs |

Ce positionnement place CARL au croisement des approches étudiées. Comme CTINexus et LADDER, il extrait automatiquement des connaissances structurées d'un texte ; comme TechniqueRAG, il restreint et vérifie la technique attribuée à chaque attaque ; comme ATAG, il s'appuie sur la littérature et sur MITRE ATLAS ; comme FALCON, il produit une défense ; et comme Self-Refine, il révise une réponse jugée insuffisante. Il s'en distingue toutefois sur deux points : la vérification n'est jamais confiée au modèle qui a produit la recommandation, et l'évaluation ne s'arrête pas à chaque étape prise isolément.

## 3.5 Contributions

Ce travail apporte deux contributions principales.

### Contribution 1 : une approche de recommandation de défenses vérifiables

La première contribution est CARL lui-même : une approche de recommandation de défenses contre les attaques visant les LLM, dont chaque réponse est vérifiable. Sa base de cas est construite automatiquement à partir d'articles scientifiques et chaque cas est rattaché à une technique MITRE ATLAS validée ; l'absence de défense documentée est enregistrée explicitement au lieu d'être comblée par le modèle ; l'adaptation de la défense s'appuie sur la chaîne causale de la nouvelle attaque ; et la vérification est séparée de la génération et confiée à une règle déterministe. Chaque recommandation est ainsi accompagnée du cas sur lequel elle repose, de la technique ATLAS de ce cas et du verdict du vérificateur. Cette propriété, que nous appelons l'auditabilité, permet à un analyste de contrôler une recommandation avant de l'appliquer.

### Contribution 2 : une mesure de la propagation des erreurs d'une étape à l'autre

La seconde contribution est méthodologique. Chaque mécanisme de contrôle de CARL vérifie une propriété facile à contrôler, que nous appelons un *proxy*, à la place de la propriété réellement recherchée : qu'un identifiant soit valide plutôt que correct, qu'un cas soit proche plutôt que pertinent, qu'une recommandation cite une source plutôt qu'elle constitue une bonne défense. Nous mesurons, étape par étape et sur les mêmes cas, l'écart entre ces deux propriétés, puis la manière dont l'erreur d'une étape se transmet aux suivantes. Cette mesure n'est possible que parce que chaque recommandation est traçable : lorsqu'une recommandation est fausse, on peut remonter jusqu'à l'étape qui a produit l'erreur. Les deux contributions sont donc liées : l'auditabilité de CARL est ce qui rend la propagation des erreurs mesurable. Les résultats de cette mesure sont présentés au chapitre 5.

## 3.6 Conclusion

La comparaison des six approches avec CARL a montré que l'état de l'art fournit des composants solides mais étudiés séparément, le plus souvent pour des menaces informatiques classiques, et qu'aucun travail ne mesure ce qui se passe lorsqu'on les enchaîne pour protéger un système fondé sur un LLM. Les cinq limites identifiées ont conduit à notre positionnement : une approche, CARL, qui réunit extraction, ancrage dans MITRE ATLAS, adaptation et vérification hors du modèle, et une évaluation qui mesure la propagation des erreurs entre ces étapes. Le chapitre suivant traduit ce positionnement en objectifs précis, puis présente la méthodologie mise en œuvre pour les atteindre : le *pipeline* global de CARL et son architecture.
