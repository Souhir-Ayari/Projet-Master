# Chapitre 6 — Discussion et limites

Le chapitre précédent a présenté les résultats de CARL étape par étape. Ce chapitre les interprète : il explique ce qu'ils montrent, répond à la problématique, situe l'apport de CARL par rapport à l'état de l'art, puis présente les limites de ce travail.

## 6.1 Interprétation des résultats : la substitution de *proxies*

Les trois questions de recherche aboutissent au même constat. À chaque étape, CARL contrôle une propriété facile à vérifier, que nous appelons un *proxy*, à la place de la propriété réellement recherchée : un identifiant **valide** à la place d'un identifiant correct, un cas **proche** à la place d'un cas pertinent, une défense **citée** à la place d'une bonne défense.

Chaque *proxy* apporte une garantie réelle. La validation empêche les identifiants inventés, le seuil écarte les requêtes clairement hors domaine, et la vérification empêche les recommandations sans source. Mais aucun ne garantit la propriété visée, et l'erreur qui reste à une étape devient l'entrée de l'étape suivante. C'est pourquoi une recommandation peut passer tous les contrôles et rester inadaptée, comme dans l'exemple du *jailbreak* encodé en Base64 : chaque contrôle est satisfait, mais l'erreur se trouve dans l'enchaînement des étapes.

Ce constat dépasse probablement CARL. Tout *pipeline* qui enchaîne extraction, classification, recherche et génération peut afficher un bon résultat à la dernière étape tout en ayant hérité d'erreurs importantes au début. Nos résultats ne permettent pas de le démontrer en général, mais ils montrent qu'il faut mesurer la validité et l'exactitude séparément, à chaque étape et sur les mêmes cas.

## 6.2 Réponse à la problématique

La problématique de ce mémoire demandait comment exploiter la littérature scientifique pour produire des recommandations de défense précises, contextualisées et vérifiables, en maîtrisant les hallucinations, le manque de granularité et les déviations des modèles de langage.

Les résultats apportent une réponse en partie positive. CARL construit automatiquement une base de cas à partir d'articles et enregistre de manière fiable l'absence de défense (« null » justifié 21 fois sur 22). Ses recommandations sont **vérifiables** : chacune cite son cas, sa technique et son article. Les **hallucinations** sont limitées : avec vérification, aucune recommandation n'est produite sans appui sur un cas, alors que le modèle seul en propose sans aucun ancrage. La **granularité** est améliorée par la chaîne causale, puisque les mesures acceptées visent un maillon précis de l'attaque. Enfin, les **déviations** liées à l'auto-validation sont évitées, puisque la vérification est confiée à une règle extérieure au modèle.

La réponse reste incomplète sur la **précision**. Une recommandation vérifiable n'est pas forcément correcte : sa qualité dépend de la classification, qui reste le point faible du *pipeline* avec un modèle de 7 milliards de paramètres. De plus, le seuil de similarité ne permet pas de savoir de façon fiable quand la base ne couvre pas une attaque.

L'apport principal de CARL n'est donc pas d'éliminer les erreurs, mais de les rendre **mesurables**. Comme chaque recommandation est traçable, il est possible de remonter jusqu'à l'étape qui a produit une erreur et de mesurer comment elle se propage. Cette mesure n'aurait pas été possible avec une génération libre.

## 6.3 Apports par rapport à l'état de l'art

Les résultats permettent de revenir sur les approches étudiées au chapitre 2.

Par rapport à **ATAG**, qui construit à la main sa base de vulnérabilités, CARL construit sa base automatiquement et mesure ce que cette automatisation coûte : 43 points de Hit@1 entre la base automatique et la base vérifiée manuellement. Cette différence correspond à ce que l'effort manuel apporte, une quantité que les bases construites à la main ne rapportent pas.

Par rapport à **FALCON** et **Self-Refine**, qui confient le contrôle au modèle générateur, nos résultats confirment le risque d'auto-approbation dans notre domaine : la critique de Self-Refine a approuvé tous ses plans initiaux, et seulement 13 % de ses recommandations sont ancrées. Le juge LLM accepte également plus de recommandations, avec une adéquation causale plus faible. La séparation entre génération et vérification est donc justifiée.

Par rapport à **TechniqueRAG**, qui restreint les techniques proposées au modèle, nos résultats montrent la limite de ce principe avec un petit modèle : la restriction empêche les identifiants inventés, mais ne suffit pas à séparer des techniques voisines comme le *jailbreak* et l'injection de *prompt*, même avec les définitions officielles.

Enfin, aucune des approches étudiées ne mesure la propagation des erreurs entre étapes. C'est l'apport méthodologique de ce travail.

## 6.4 Compromis entre couverture et solidité

Les résultats de RQ3 font apparaître un compromis. Un vérificateur strict, comme la règle causale avec étiquettes aux seuils fixés a priori, ne retient que des mesures causalement adéquates, mais ne sert que 3 requêtes sur 13. À l'inverse, une critique par le même modèle sert toutes les requêtes, parce qu'elle ne rejette rien. Les seuils calibrés se situent entre les deux, avec 7 requêtes servies.

Il n'existe donc pas de « meilleur » vérificateur dans l'absolu : chaque configuration est un point entre couverture et solidité. Dans un contexte de sécurité, nous considérons qu'il est préférable de ne pas répondre plutôt que de proposer une défense inadaptée. Ce choix doit toutefois être annoncé avec le nombre de requêtes laissées sans réponse, et non caché derrière un ancrage de 1,00.

## 6.5 Limites

**Taille du corpus.** La base contient 119 cas extraits de 14 articles, et l'évaluation repose sur 18 requêtes. Le corpus est dominé par le *jailbreak* et l'injection de *prompt*, et plusieurs techniques ATLAS n'ont qu'un seul cas. Les résultats sont donc indicatifs : ils ne prétendent pas couvrir l'ensemble des attaques contre les LLM, et la structure des confusions observées peut être propre à cette répartition.

**Annotation unique.** La revue des cas, qui sert de référence pour RQ1 et RQ2, a été pré-annotée avec un assistant LLM puis vérifiée par une seule personne, qui est aussi l'auteure du système. L'accord mesuré est un accord intra-annotateur (kappa de 0,62 pour la technique et de 0,75 pour la défense) : il indique la cohérence de la revue, mais pas son absence de biais. Les taux d'exactitude doivent donc être lus comme des bornes supérieures, et la base de référence comme une borne optimiste. Les mesures de propagation héritent de ces limites.

**Modèle utilisé.** Un modèle de 7 milliards de paramètres ne sépare pas des techniques voisines. Sa génération varie aussi d'une exécution à l'autre, même avec une température de 0,1 : une seconde exécution de notre configuration a donné 14 recommandations sur 9 requêtes au lieu de 9 sur 7. Nous ne savons pas si un modèle plus grand réduirait l'écart entre validité et exactitude.

**Mesures fragiles.** L'extraction a été évaluée sur un seul article annoté, dont l'annotation s'est révélée incomplète. Les seuils du vérificateur causal ont été calibrés sur 20 paires seulement, et le seuil sémantique sépare mal les exemples positifs et négatifs. La mesure d'hallucination est une mesure légère, propre au domaine, et non un instrument validé.

**Évaluation humaine.** Elle repose sur deux évaluateurs seulement, qui n'ont pas reçu exactement les mêmes documents, et leur accord est inférieur au hasard. Elle ne permet aucun classement des configurations.

**Composants non évalués.** Deux composants de l'architecture sont implémentés mais n'ont pas été évalués. La recherche secondaire d'articles, qui devait enrichir la base lorsque aucun cas n'est assez proche, est restée désactivée ; l'étape de conservation des nouveaux cas n'est donc validée que pour la construction hors ligne. La génération de variantes adverses, qui testerait si une défense résiste réellement à l'attaque, est seulement décrite. C'est pourtant la piste la plus directe pour réduire l'écart entre traçabilité et solidité.

## 6.6 Conclusion

Les résultats de CARL s'expliquent par une même substitution de *proxies*, répétée à chaque étape et propagée d'une étape à l'autre. CARL répond en partie à la problématique : ses recommandations sont vérifiables, traçables et mieux ciblées, mais leur précision reste limitée par la classification. Son apport principal est de rendre ces erreurs mesurables. Ces conclusions doivent être lues à la lumière des limites présentées, en particulier la taille du corpus et l'annotation unique. La conclusion générale reprend ces apports et propose des perspectives.
