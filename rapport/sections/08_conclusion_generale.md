# Conclusion générale et perspectives

Ce mémoire est parti d'un constat : les attaques contre les LLM, comme l'injection de *prompt*, le *jailbreak* ou l'empoisonnement des données, sont documentées dans une littérature scientifique abondante et en évolution rapide, mais un analyste ne peut pas la lire et la transformer à la main en mesures de défense. Laisser un modèle de langage générer librement ces défenses n'est pas une solution satisfaisante, car le modèle peut produire des recommandations non fondées, trop générales, ou valider ses propres erreurs.

Pour répondre à ce problème, nous avons proposé CARL (*Case-based Attack Remediation for LLMs*), une approche fondée sur le raisonnement à partir de cas. CARL construit automatiquement une base de cas à partir d'articles scientifiques : GLiNER extrait les entités, Mistral-7B résume l'attaque et la défense, et chaque cas est rattaché à une technique MITRE ATLAS validée, avec une valeur « null » explicite lorsque l'article ne propose aucune défense. Face à une nouvelle attaque, CARL la décrit par sa chaîne causale, retrouve les cas les plus proches, adapte leur défense au maillon de l'attaque qu'elle doit casser, puis vérifie la recommandation par une règle déterministe, extérieure au modèle.

**Bilan des résultats.** L'évaluation a porté sur chaque étape séparément, sur les mêmes cas, à partir d'une base de 119 cas extraits de 14 articles et de 18 requêtes de test. Elle montre qu'à chaque étape, le contrôle de CARL vérifie une propriété plus faible que celle recherchée :

- **classer** : 89,9 % des identifiants ATLAS sont valides, mais seulement 47,5 % sont corrects ; le modèle confond surtout le *jailbreak* et l'injection de *prompt* ;
- **chercher** : le premier cas retrouvé n'est pertinent que pour 57,1 % des requêtes, contre 100 % lorsque les techniques sont corrigées ; les erreurs de classification coûtent 43 points, et le seuil de similarité ne signale pas de manière fiable les attaques non couvertes ;
- **vérifier** : toutes les recommandations retenues sont ancrées (1,00), mais une recommandation peut citer un cas et rester inadaptée à l'attaque.

Ces écarts ne restent pas isolés : l'erreur d'une étape devient l'entrée de la suivante. C'est ce que nous avons appelé la substitution de *proxies*.

**Contributions.** Ce travail apporte deux contributions. La première est une approche de recommandation dont chaque réponse est **vérifiable** : elle est accompagnée du cas cité, de sa technique ATLAS, de son article d'origine et du verdict du vérificateur. La seconde est **méthodologique** : grâce à cette traçabilité, il devient possible de mesurer où naît une erreur et comment elle se propage d'une étape à l'autre.

CARL est donc vérifiable, mais pas sûr par nature : c'est sa traçabilité qui permet de mesurer l'erreur. Ce résultat rappelle qu'un bon score à la dernière étape d'un *pipeline* ne suffit pas, et qu'il faut mesurer séparément, à chaque étape, ce que le système vérifie et ce qu'il est censé garantir.

**Perspectives.** Les limites mises en évidence ouvrent plusieurs pistes de travail.

**Améliorer la classification.** La classification est le point faible du *pipeline*, et son erreur se propage aux étapes suivantes. Une première piste consiste à tester des modèles plus grands, ou à mieux séparer les techniques voisines comme le *jailbreak* et l'injection de *prompt*. Il faudra vérifier si l'écart entre validité et exactitude diminue réellement.

**Trouver un meilleur signal de couverture.** La similarité seule ne permet pas de savoir quand la base ne couvre pas une attaque. Un autre critère devra être étudié, afin que CARL sache dire de façon fiable qu'il ne connaît pas une attaque.

**Activer la recherche secondaire d'articles.** Ce composant, implémenté mais désactivé dans ce travail, permettrait d'enrichir la base lorsqu'une attaque n'est pas couverte, et de valider l'étape de conservation des nouveaux cas. Il dépend toutefois d'un signal de couverture fiable.

**Tester la robustesse des défenses.** La vérification actuelle contrôle le lien entre une mesure et sa source, mais pas son efficacité. La génération de variantes adverses de l'attaque, conçues pour contourner la défense proposée, permettrait de vérifier si la mesure résiste réellement. C'est la piste la plus directe pour réduire l'écart entre traçabilité et solidité.

**Renforcer l'évaluation.** Les conclusions de ce travail devront être confirmées sur un corpus plus large et plus varié, couvrant d'autres tactiques ATLAS. La revue des cas devra être reprise par un annotateur indépendant, et l'évaluation humaine menée avec davantage d'évaluateurs, de préférence des spécialistes de la sécurité, qui reçoivent exactement les mêmes documents.
