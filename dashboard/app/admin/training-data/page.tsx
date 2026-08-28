"use client";

import "./training-data.css";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { defineMessages, formatMessage, LanguageSwitcher, useLocale } from "../../i18n";

const messages = defineMessages({
  documentTitle: "Training Data Lab — CrisisPulse Admin",
  documentDescription: "Inspect the locally reviewed article dataset, training eligibility, class balance, and future model gates.",
  brandHome: "CrisisPulse dashboard home",
  primaryNavigation: "Primary navigation",
  dashboard: "Dashboard",
  admin: "Admin",
  trainingData: "Training data",
  localDataset: "Local reviewed dataset",
  heroTitle: "Turn careful review into a dataset we can trust.",
  heroDescription: "See every latest article label, understand what is eligible for training, and correct class imbalance before any model experiment begins.",
  liveFromLocalApi: "Live from local API",
  checkingLocalApi: "Checking local API",
  localApiUnavailable: "Local API unavailable",
  refresh: "Refresh data",
  refreshing: "Refreshing…",
  exportCsv: "Download training CSV",
  auditExternalData: "Audit outside datasets",
  readinessOverview: "Readiness overview",
  readinessHeading: "Two planning gates, not quality guarantees.",
  readinessDescription: "The gates prevent premature experiments. Reaching either count does not prove accuracy, usefulness, or product safety.",
  eligibleLabels: "Eligible labels",
  excludedLabels: "Excluded labels",
  latestReviews: "Latest reviews",
  smallestClass: "Smallest resolved class",
  eligibleDefinition: "Detailed version-2 labels in one of the four resolved classes.",
  excludedDefinition: "Uncertain or older labels remain auditable but do not train the classifier.",
  currentDatasetDefinition: "One current row per article after append-only corrections.",
  smallestClassDefinition: "The rarest class controls whether the balance gate passes.",
  cpuGate: "CPU baseline gate",
  gpuGate: "RTX 4070 experiment gate",
  notReady: "Not ready",
  requirementMet: "Met",
  requirementPending: "Pending",
  notComputable: "Not computable",
  cpuGatePendingHelp: "A CPU experiment stays blocked until every count and audit below passes. Labels alone cannot clear this gate.",
  gpuGatePendingHelp: "GPU training is not ready. It remains blocked until every data, diversity, agreement, and feature-parity audit passes.",
  labelsTotalProgress: "{current} of {target} eligible labels",
  labelsClassProgress: "Smallest class: {current} of {target}",
  countRequirement: "{current} / {target}",
  eligibleLabelRequirement: "Resolved version-2 labels",
  classMinimumRequirement: "Minimum in each resolved class",
  articleDaysRequirement: "Distinct article seen_at days",
  publisherRequirement: "Distinct publisher groups",
  inferenceTextRequirement: "Inference-available article text",
  featureParityRequirement: "Training/inference feature parity",
  splitViabilityRequirement: "Leakage-safe train / validation / test split",
  splitGateValue: "Smallest class: train {training}, validation {validation}, final test {test}",
  baselineEvidenceRequirement: "CPU gain over the deterministic baseline",
  baselineEvidenceTarget: "≥0.05 macro-F1; publisher/story bootstrap CI > 0",
  cpuBaselineRequirement: "Proven CPU baseline before any GPU experiment",
  cpuBaselinePending: "Blocked until the CPU gate and baseline comparison both pass",
  doubleReviewRequirement: "Double-reviewed, adjudicated examples (25/class minimum)",
  kappaRequirement: "Adjudicated Cohen’s kappa",
  percentageRequirement: "At least {target}%",
  boundariesHeading: "What these labels can and cannot prove",
  measurementBoundary: "Twenty resolved labels unlock only a preliminary filter measurement. They do not make a dataset ready for model training.",
  uncertainBoundary: "Cannot determine is retained as an abstention challenge, not treated as a fifth semantic training class.",
  balanceBoundary: "The daily review queue is deliberately balanced. Its class mix is not real-world prevalence and does not prove accuracy.",
  scopeBoundary: "A future classifier would label evidence in an article. It would not verify that a physical flood occurred.",
  forecastBoundary: "This article classifier is separate from CrisisPulse’s media-spread forecast and its chronological holdout.",
  modelInputsBoundary: "Future model input is frozen, inference-available headline and URL-path text. source_domain is split and error-analysis metadata; match_strength, review_bucket, tags, and reviewed_at are not model inputs.",
  splitBoundary: "Split by article seen_at, group syndicated stories and normalized publisher families, and keep the newest publisher/story holdout untouched until final evaluation.",
  qualityCaveat: "Meeting a planning gate only means there is enough labeled material to run the next experiment. It does not prove model quality.",
  hardwareHeading: "Locally verified hardware",
  hardwareHelp: "Hardware note recorded on this PC; this is not live monitoring.",
  gpuName: "NVIDIA GeForce RTX 4070",
  gpuMemory: "12,282 MiB VRAM",
  gpuCapability: "Compute capability 8.9",
  cudaVersion: "CUDA UMD 13.3",
  noGpuJob: "No GPU training job is configured yet.",
  cpuRunnerReady: "Guarded CPU baseline runner installed.",
  cpuRunnerHelp: "It starts with a readiness check and refuses incompatible, legacy, uncertain, or leakage-prone data.",
  trainingAttemptEyebrow: "Latest local training attempt",
  trainingAttemptHeading: "See exactly what the local training runner decided.",
  trainingAttemptDescription: "This is the saved result from the local CPU training pipeline, not an estimate based only on label totals.",
  modelStoryEyebrow: "How the model learns",
  modelStoryHeading: "From your labels to an honestly tested classifier.",
  modelStoryDescription: "This is a small, local four-category classifier—not a ChatGPT-style generative model. The diagrams below use current labels and the last saved runner attempt.",
  modelStatusCollecting: "Current stage: collecting and balancing labels",
  modelPlainHeading: "What will actually be trained",
  modelPlainHelp: "CrisisPulse turns trusted headline and URL-path text into word and character patterns, then fits a class-balanced logistic-regression classifier on the CPU. It may abstain when confidence is low. The GPU stays out of the process until a CPU baseline proves useful.",
  modelFlowAria: "Five stages in the CrisisPulse article-classifier workflow",
  modelFlowHuman: "Human labels",
  modelFlowHumanHelp: "You assign one of four article meanings.",
  modelFlowText: "Safe text",
  modelFlowTextHelp: "Only headline and URL-path text available during live use are kept.",
  modelFlowSplit: "Time-safe split",
  modelFlowSplitHelp: "Older articles train; later stories and publishers validate and test.",
  modelFlowFit: "CPU classifier",
  modelFlowFitHelp: "Word and character TF-IDF feed balanced logistic regression.",
  modelFlowEvaluate: "Honest comparison",
  modelFlowEvaluateHelp: "Compare with simple rules, protect the final test, and allow abstention.",
  currentBalanceChartHeading: "Current reviewed label balance",
  currentBalanceChartHelp: "Live latest-label counts. This deliberately reviewed sample is not real-world flood prevalence.",
  savedSplitChartHeading: "Last attempt: where each class landed",
  savedSplitChartHelp: "A usable model needs every class in training, validation, and the untouched final test.",
  savedSplitUnavailable: "No three-way split is available in the last saved attempt yet.",
  savedAttemptUnavailable: "No saved attempt is available for this chart yet.",
  snapshotDifferent: "The saved attempt used {attempt} reviews; the live dataset now has {current}. The attempt charts and map remain labeled as a snapshot.",
  splitGap: "Missing from one or more train, validation, or final-test periods: {classes}.",
  noSplitGap: "Every class appears in all three periods.",
  mapHeading: "Locations mentioned in the last training attempt",
  mapHelp: "Pins show approximate primary places mentioned in reviewed articles. They are not verified flood events.",
  mapMapped: "{plotted} plotted of {mapped} safely mappable rows",
  mapExcluded: "{count} ambiguous, missing, or invalid locations excluded",
  mapLoading: "Loading public-domain world boundaries…",
  mapUnavailable: "No trustworthy map locations are available in this saved attempt yet.",
  mapBoundaryUnavailable: "World boundaries could not be loaded; the coordinate pins remain available in the list.",
  mapLocationAria: "{location}: {count} reviewed articles; {category}",
  mapLocationCount: "{count} reviewed articles",
  mapListHeading: "Mapped locations",
  mapListShowing: "Showing {shown} of {total} locations",
  mapTruncated: "The saved report returns its top {returned} of {total} locations; {rows} safely mappable rows are outside this view.",
  mapLegendHeading: "Pin color",
  mapMixed: "Mixed classes / tie",
  mapSelected: "Selected location",
  mapMeaningNote: "Map source: GDELT primary article location. Only single-region or dominant-region coordinates are plotted; ambiguous coordinates are excluded.",
  naturalEarthAttribution: "Basemap boundaries: Natural Earth (public domain)",
  attemptChecking: "Checking the latest saved training attempt…",
  attemptMissingHeading: "No local training attempt has been saved yet.",
  attemptMissingHelp: "The guarded runner can create a readiness report without fitting a model or spending API credits.",
  attemptUnavailableHeading: "The saved training result is temporarily unavailable.",
  attemptUnavailableHelp: "Your labels are safe. Refresh after the local API is available.",
  attemptStale: "The refresh failed; the last saved training result is still shown.",
  attemptStopped: "Stopped safely",
  attemptReady: "Ready for the next local run",
  attemptCompleted: "Local experiment completed",
  attemptReadinessOnly: "Readiness check complete",
  noModelCreated: "No model was created",
  modelCreated: "Experimental model created",
  attemptSaved: "Saved {time}",
  attemptWhyStopped: "The runner did not fit a model because every class must be represented in training, validation, and final testing. Add more reviewed examples—especially to the smallest class—and run the check again.",
  attemptReadyHelp: "The selected checks passed. The next run may fit an experimental local model, but it will still need an untouched evaluation before product use.",
  attemptCompletedHelp: "Treat these results as an experiment, not proof that the classifier is ready for customers.",
  attemptCountsHeading: "Data used by the runner",
  attemptLatestReviews: "Latest reviews",
  attemptResolvedReviews: "Resolved version-2 labels",
  attemptUsableRows: "Rows with safe input text",
  attemptExcludedRows: "Excluded safely",
  attemptClassHeading: "Usable rows by class",
  attemptSplitHeading: "Leakage-safe chronological split",
  attemptSplitHelp: "Stories are grouped and final-test publishers are removed from earlier periods.",
  attemptSplitUnavailable: "The data cannot yet support three safe periods.",
  attemptTrainingRows: "Training",
  attemptValidationRows: "Validation",
  attemptTestRows: "Final test",
  attemptGateHeading: "Checks from this attempt",
  attemptSmokeChecks: "Small pipeline smoke-test checks",
  attemptProductionChecks: "Real CPU experiment checks",
  attemptGatePassed: "Passed",
  attemptGateFailed: "Needs more data",
  attemptGateValue: "{actual} / {minimum}",
  attemptGateYes: "Yes",
  attemptGateNo: "No",
  gateTotalUsableRows: "Total usable rows",
  gateMinimumClass: "Rows in the smallest class",
  gateDistinctDates: "Distinct article dates",
  gatePublisherGroups: "Distinct publisher groups",
  gateInferenceCoverage: "Safe text available at live inference",
  gateTrainingClass: "Smallest class in training",
  gateValidationClass: "Smallest class in validation",
  gateTestClass: "Smallest class in final test",
  gateSplitComputable: "Three-way safe split can be created",
  classBalance: "Class balance",
  classBalanceHeading: "Every resolved class must carry its share.",
  classBalanceDescription: "A high total can hide a weak class. Each bar is checked against both planning gates.",
  reportedFlooding: "Flooding reported",
  floodRiskWarning: "Flood risk / warning",
  heavyRainOnly: "Heavy rain only",
  notFloodRelated: "Not flood-related",
  uncertain: "Cannot determine",
  legacyLabel: "Older label",
  classCount: "{count} eligible labels",
  cpuMinimum: "CPU minimum",
  gpuMinimum: "GPU minimum",
  smartReviewEyebrow: "Close the next data gap",
  smartReviewHeading: "Review the highest-value cards next.",
  smartReviewDescription: "Admin keeps unfinished cards stable, removes completed cards, and refills open places with archive-backed selections that improve label balance, date, publisher, inference-text, or split coverage.",
  smartReviewHint: "The queue never reveals a guessed label. Your independent, evidence-based decision is the only answer saved for training.",
  openSmartReviewQueue: "Open smart review queue",
  eligibilityHeading: "What is usable today",
  eligibilityDescription: "Excluded reviews are preserved so nothing is erased. They need a detailed correction before they can enter training.",
  eligibleForTraining: "Eligible for training",
  excludedUncertain: "Excluded: cannot determine",
  excludedLegacy: "Excluded: older schema",
  exclusionMismatch: "Other excluded records",
  archiveFunnel: "Collection-to-training funnel",
  archiveFunnelHeading: "More collected articles do not automatically become training examples.",
  archiveFunnelDescription: "Each stage narrows the material. Human review is the bridge between the permanent archive and an eligible model row.",
  rawArchive: "Retained raw GDELT archive",
  rawArchiveDetail: "{bytes} across {files} compressed files",
  permanentArticles: "Permanently archived articles",
  permanentArticlesHelp: "Stored publisher records available for sampling",
  reviewedLabels: "Latest reviewed labels",
  reviewedLabelsHelp: "One current decision per reviewed article",
  eligibleRows: "Eligible training rows",
  eligibleRowsHelp: "Resolved version-2 labels only",
  liveFunnelUnavailable: "Live archive status is temporarily unavailable",
  dataFlow: "Data flow",
  dataFlowHeading: "From a publisher story to a future experiment.",
  dataFlowDescription: "This page is an inspection and export tool. It does not start a training job.",
  flowReview: "Review the article",
  flowReviewHelp: "A person chooses one primary label and may add context tags.",
  flowLatest: "Keep the latest correction",
  flowLatestHelp: "The audit log stays append-only; the dataset uses the newest decision per article.",
  flowEligibility: "Apply eligibility rules",
  flowEligibilityHelp: "Only the four resolved version-2 classes enter the training pool.",
  flowExperiment: "Export, split, then test",
  flowExperimentHelp: "A future job must create leakage-safe train, validation, and holdout periods before fitting.",
  creditHeading: "What uses credits",
  creditLocal: "Reading this page and running future training locally on this PC do not use ChatGPT credits. Local compute still uses electricity.",
  creditCodex: "Work you ask Codex to perform does use your Codex or ChatGPT allowance. A future cloud GPU would have a separate provider cost.",
  datasetExplorer: "Dataset explorer",
  datasetExplorerHeading: "Inspect the rows behind the totals.",
  datasetExplorerDescription: "Search and filter locally. The CSV download always exports the complete latest-label dataset from the API.",
  search: "Search articles",
  searchPlaceholder: "Title, publisher, ID, or context tag",
  labelFilter: "Primary label",
  eligibilityFilter: "Eligibility",
  allLabels: "All labels",
  allRows: "All rows",
  eligibleOnly: "Eligible only",
  excludedOnly: "Excluded only",
  clearFilters: "Clear filters",
  resultsCount: "Showing {visible} of {total} rows",
  easternTime: "Review times use U.S. Eastern Time.",
  articleColumn: "Article",
  publisherColumn: "Publisher",
  labelColumn: "Primary label",
  tagsColumn: "Context tags",
  reviewedColumn: "Reviewed",
  eligibilityColumn: "Training eligibility",
  articleTableCaption: "Latest reviewed article labels and training eligibility",
  noTitle: "Untitled article",
  unknownPublisher: "Unknown publisher",
  noTags: "No context tags",
  eligible: "Eligible",
  excluded: "Excluded",
  legacyReason: "Needs a detailed version-2 correction",
  uncertainReason: "Cannot determine is preserved but excluded",
  otherExclusionReason: "Excluded by the current dataset rules",
  openPublisherStory: "Open publisher story: {title}",
  loadingHeading: "Loading the local training dataset…",
  loadingHelp: "CrisisPulse is checking the latest saved article labels.",
  errorHeading: "The training dataset could not be loaded.",
  errorHelp: "Make sure the local CrisisPulse API is running, then try again. No data was changed.",
  retry: "Try again",
  emptyHeading: "No reviewed articles are available yet.",
  emptyHelp: "Complete article reviews in Admin. Eligible and excluded rows will appear here after they are saved.",
  filteredEmptyHeading: "No rows match these filters.",
  filteredEmptyHelp: "Change the search or clear the filters to see the full dataset.",
  lastLoaded: "Last checked {time}",
  safeReadOnly: "Read-only dataset view",
  safeReadOnlyHelp: "This page cannot delete reviews, relabel articles, start training, or change alerts.",
}, {
  documentTitle: "Laboratorio de datos de entrenamiento — Administración de CrisisPulse",
  documentDescription: "Inspeccione el conjunto local de artículos revisados, la elegibilidad, el equilibrio de clases y los umbrales para modelos futuros.",
  brandHome: "Inicio del panel de CrisisPulse",
  primaryNavigation: "Navegación principal",
  dashboard: "Panel",
  admin: "Administración",
  trainingData: "Datos de entrenamiento",
  localDataset: "Conjunto local revisado",
  heroTitle: "Convierta una revisión cuidadosa en datos confiables.",
  heroDescription: "Vea la etiqueta más reciente de cada artículo, entienda qué puede entrenar un modelo y corrija el desequilibrio antes de experimentar.",
  liveFromLocalApi: "En vivo desde la API local",
  checkingLocalApi: "Comprobando la API local",
  localApiUnavailable: "API local no disponible",
  refresh: "Actualizar datos",
  refreshing: "Actualizando…",
  exportCsv: "Descargar CSV de entrenamiento",
  auditExternalData: "Auditar conjuntos externos",
  readinessOverview: "Resumen de preparación",
  readinessHeading: "Dos umbrales de planificación, no garantías de calidad.",
  readinessDescription: "Los umbrales evitan experimentos prematuros. Alcanzar un conteo no demuestra precisión, utilidad ni seguridad del producto.",
  eligibleLabels: "Etiquetas elegibles",
  excludedLabels: "Etiquetas excluidas",
  latestReviews: "Revisiones más recientes",
  smallestClass: "Clase resuelta más pequeña",
  eligibleDefinition: "Etiquetas detalladas de versión 2 en una de las cuatro clases resueltas.",
  excludedDefinition: "Las etiquetas inciertas o anteriores siguen auditables, pero no entrenan el clasificador.",
  currentDatasetDefinition: "Una fila vigente por artículo después de correcciones de solo anexado.",
  smallestClassDefinition: "La clase menos frecuente controla si se alcanza el equilibrio.",
  cpuGate: "Umbral del modelo base en CPU",
  gpuGate: "Umbral del experimento con RTX 4070",
  notReady: "No está listo",
  requirementMet: "Cumplido",
  requirementPending: "Pendiente",
  notComputable: "No se puede calcular",
  cpuGatePendingHelp: "El experimento en CPU sigue bloqueado hasta que se cumplan todos los conteos y auditorías. Las etiquetas por sí solas no abren este umbral.",
  gpuGatePendingHelp: "El entrenamiento con GPU no está listo. Sigue bloqueado hasta aprobar todas las auditorías de datos, diversidad, acuerdo y paridad de características.",
  labelsTotalProgress: "{current} de {target} etiquetas elegibles",
  labelsClassProgress: "Clase más pequeña: {current} de {target}",
  countRequirement: "{current} / {target}",
  eligibleLabelRequirement: "Etiquetas resueltas de versión 2",
  classMinimumRequirement: "Mínimo en cada clase resuelta",
  articleDaysRequirement: "Días distintos de seen_at del artículo",
  publisherRequirement: "Grupos de editores distintos",
  inferenceTextRequirement: "Texto de artículo disponible para inferencia",
  featureParityRequirement: "Paridad de características entre entrenamiento e inferencia",
  splitViabilityRequirement: "División sin filtraciones entre entrenamiento, validación y prueba",
  splitGateValue: "Clase más pequeña: entrenamiento {training}, validación {validation}, prueba final {test}",
  baselineEvidenceRequirement: "Mejora del modelo en CPU sobre la base determinista",
  baselineEvidenceTarget: "≥0.05 macro-F1; IC bootstrap por editor/historia > 0",
  cpuBaselineRequirement: "Modelo base en CPU comprobado antes de experimentar con GPU",
  cpuBaselinePending: "Bloqueado hasta aprobar el umbral en CPU y la comparación con la base",
  doubleReviewRequirement: "Ejemplos con doble revisión y adjudicación (mínimo 25/clase)",
  kappaRequirement: "Kappa de Cohen después de adjudicación",
  percentageRequirement: "Al menos {target}%",
  boundariesHeading: "Qué pueden y qué no pueden demostrar estas etiquetas",
  measurementBoundary: "Veinte etiquetas resueltas solo habilitan una medición preliminar del filtro. No preparan un conjunto para entrenar un modelo.",
  uncertainBoundary: "No se puede determinar se conserva como reto de abstención, no como una quinta clase semántica de entrenamiento.",
  balanceBoundary: "La cola diaria está equilibrada a propósito. Su mezcla de clases no representa la prevalencia real ni demuestra precisión.",
  scopeBoundary: "Un clasificador futuro etiquetaría la evidencia en un artículo. No verificaría que ocurrió una inundación física.",
  forecastBoundary: "Este clasificador de artículos es independiente del pronóstico de difusión mediática de CrisisPulse y de su reserva cronológica.",
  modelInputsBoundary: "La entrada futura del modelo será el texto congelado y disponible en inferencia del titular y de la ruta URL. source_domain servirá para dividir y analizar errores; match_strength, review_bucket, tags y reviewed_at no serán entradas del modelo.",
  splitBoundary: "La división usará seen_at del artículo, agrupará historias sindicadas y familias normalizadas de editores, y mantendrá intacta la reserva más reciente por editor e historia hasta la evaluación final.",
  qualityCaveat: "Alcanzar un umbral solo indica que hay material etiquetado suficiente para el siguiente experimento. No demuestra la calidad del modelo.",
  hardwareHeading: "Hardware verificado localmente",
  hardwareHelp: "Nota registrada en esta PC; no es monitoreo en vivo.",
  gpuName: "NVIDIA GeForce RTX 4070",
  gpuMemory: "12,282 MiB de VRAM",
  gpuCapability: "Capacidad de cómputo 8.9",
  cudaVersion: "CUDA UMD 13.3",
  noGpuJob: "Todavía no hay una tarea de entrenamiento con GPU configurada.",
  cpuRunnerReady: "Motor base protegido para CPU instalado.",
  cpuRunnerHelp: "Primero comprueba la preparación y rechaza datos incompatibles, antiguos, inciertos o con filtraciones.",
  trainingAttemptEyebrow: "Intento local más reciente",
  trainingAttemptHeading: "Vea exactamente qué decidió el motor local de entrenamiento.",
  trainingAttemptDescription: "Este es el resultado guardado del proceso local en CPU, no una estimación basada solo en el total de etiquetas.",
  modelStoryEyebrow: "Cómo aprende el modelo",
  modelStoryHeading: "De sus etiquetas a un clasificador evaluado con honestidad.",
  modelStoryDescription: "Este es un pequeño clasificador local de cuatro categorías, no un modelo generativo como ChatGPT. Los diagramas usan las etiquetas actuales y el último intento guardado.",
  modelStatusCollecting: "Etapa actual: recopilar y equilibrar etiquetas",
  modelPlainHeading: "Qué se entrenará realmente",
  modelPlainHelp: "CrisisPulse convierte el titular confiable y la ruta URL en patrones de palabras y caracteres, y ajusta en la CPU un clasificador de regresión logística equilibrado. Puede abstenerse cuando la confianza sea baja. La GPU queda fuera hasta que una base en CPU demuestre utilidad.",
  modelFlowAria: "Cinco etapas del clasificador de artículos de CrisisPulse",
  modelFlowHuman: "Etiquetas humanas",
  modelFlowHumanHelp: "Usted asigna uno de cuatro significados del artículo.",
  modelFlowText: "Texto seguro",
  modelFlowTextHelp: "Solo se conserva el titular y la ruta URL disponibles durante el uso en vivo.",
  modelFlowSplit: "División temporal segura",
  modelFlowSplitHelp: "Los artículos anteriores entrenan; historias y editores posteriores validan y prueban.",
  modelFlowFit: "Clasificador en CPU",
  modelFlowFitHelp: "TF-IDF de palabras y caracteres alimenta una regresión logística equilibrada.",
  modelFlowEvaluate: "Comparación honesta",
  modelFlowEvaluateHelp: "Se compara con reglas simples, se protege la prueba final y se permite abstenerse.",
  currentBalanceChartHeading: "Equilibrio actual de etiquetas revisadas",
  currentBalanceChartHelp: "Conteos vigentes en vivo. Esta muestra revisada a propósito no representa la prevalencia real de inundaciones.",
  savedSplitChartHeading: "Último intento: dónde quedó cada clase",
  savedSplitChartHelp: "Un modelo utilizable necesita cada clase en entrenamiento, validación y la prueba final intacta.",
  savedSplitUnavailable: "El último intento guardado todavía no tiene una división en tres partes.",
  savedAttemptUnavailable: "Todavía no hay un intento guardado para este gráfico.",
  snapshotDifferent: "El intento guardado usó {attempt} revisiones; el conjunto en vivo ahora tiene {current}. Los gráficos y el mapa del intento siguen identificados como una captura.",
  splitGap: "Faltan en uno o más periodos de entrenamiento, validación o prueba final: {classes}.",
  noSplitGap: "Todas las clases aparecen en los tres periodos.",
  mapHeading: "Lugares mencionados en el último intento de entrenamiento",
  mapHelp: "Los puntos muestran lugares principales aproximados mencionados en artículos revisados. No son eventos de inundación verificados.",
  mapMapped: "{plotted} trazadas de {mapped} filas ubicables con seguridad",
  mapExcluded: "{count} ubicaciones ambiguas, ausentes o inválidas excluidas",
  mapLoading: "Cargando límites mundiales de dominio público…",
  mapUnavailable: "Todavía no hay ubicaciones confiables para el mapa en este intento guardado.",
  mapBoundaryUnavailable: "No se pudieron cargar los límites mundiales; los puntos siguen disponibles en la lista.",
  mapLocationAria: "{location}: {count} artículos revisados; {category}",
  mapLocationCount: "{count} artículos revisados",
  mapListHeading: "Ubicaciones en el mapa",
  mapListShowing: "Mostrando {shown} de {total} ubicaciones",
  mapTruncated: "El informe guardado devuelve sus {returned} ubicaciones principales de {total}; {rows} filas ubicables quedan fuera de esta vista.",
  mapLegendHeading: "Color de los puntos",
  mapMixed: "Clases mixtas / empate",
  mapSelected: "Ubicación seleccionada",
  mapMeaningNote: "Fuente del mapa: ubicación principal del artículo en GDELT. Solo se trazan coordenadas de región única o dominante; las ambiguas se excluyen.",
  naturalEarthAttribution: "Límites del mapa: Natural Earth (dominio público)",
  attemptChecking: "Comprobando el último intento guardado…",
  attemptMissingHeading: "Todavía no hay un intento local guardado.",
  attemptMissingHelp: "El motor protegido puede crear un informe de preparación sin ajustar un modelo ni gastar créditos de API.",
  attemptUnavailableHeading: "El resultado guardado no está disponible temporalmente.",
  attemptUnavailableHelp: "Sus etiquetas están seguras. Actualice cuando la API local esté disponible.",
  attemptStale: "Falló la actualización; se sigue mostrando el último resultado guardado.",
  attemptStopped: "Detenido de forma segura",
  attemptReady: "Listo para la siguiente ejecución local",
  attemptCompleted: "Experimento local completado",
  attemptReadinessOnly: "Comprobación de preparación terminada",
  noModelCreated: "No se creó ningún modelo",
  modelCreated: "Se creó un modelo experimental",
  attemptSaved: "Guardado {time}",
  attemptWhyStopped: "El motor no ajustó un modelo porque cada clase debe aparecer en entrenamiento, validación y prueba final. Añada más ejemplos revisados—especialmente en la clase más pequeña—y vuelva a ejecutar la comprobación.",
  attemptReadyHelp: "Las comprobaciones seleccionadas se cumplieron. La siguiente ejecución puede ajustar un modelo local experimental, pero todavía necesitará una evaluación intacta antes de usarse en el producto.",
  attemptCompletedHelp: "Considere estos resultados un experimento, no una prueba de que el clasificador esté listo para clientes.",
  attemptCountsHeading: "Datos utilizados por el motor",
  attemptLatestReviews: "Revisiones más recientes",
  attemptResolvedReviews: "Etiquetas resueltas de versión 2",
  attemptUsableRows: "Filas con texto seguro",
  attemptExcludedRows: "Excluidas de forma segura",
  attemptClassHeading: "Filas utilizables por clase",
  attemptSplitHeading: "División cronológica sin filtraciones",
  attemptSplitHelp: "Las historias se agrupan y los editores de la prueba final se eliminan de periodos anteriores.",
  attemptSplitUnavailable: "Los datos todavía no permiten crear tres periodos seguros.",
  attemptTrainingRows: "Entrenamiento",
  attemptValidationRows: "Validación",
  attemptTestRows: "Prueba final",
  attemptGateHeading: "Comprobaciones de este intento",
  attemptSmokeChecks: "Comprobaciones pequeñas del proceso",
  attemptProductionChecks: "Comprobaciones del experimento real en CPU",
  attemptGatePassed: "Cumplido",
  attemptGateFailed: "Necesita más datos",
  attemptGateValue: "{actual} / {minimum}",
  attemptGateYes: "Sí",
  attemptGateNo: "No",
  gateTotalUsableRows: "Total de filas utilizables",
  gateMinimumClass: "Filas en la clase más pequeña",
  gateDistinctDates: "Fechas distintas de artículos",
  gatePublisherGroups: "Grupos distintos de editores",
  gateInferenceCoverage: "Texto seguro disponible durante la inferencia",
  gateTrainingClass: "Clase más pequeña en entrenamiento",
  gateValidationClass: "Clase más pequeña en validación",
  gateTestClass: "Clase más pequeña en la prueba final",
  gateSplitComputable: "Se puede crear una división segura en tres partes",
  classBalance: "Equilibrio de clases",
  classBalanceHeading: "Cada clase resuelta debe aportar su parte.",
  classBalanceDescription: "Un total alto puede ocultar una clase débil. Cada barra se compara con ambos umbrales de planificación.",
  reportedFlooding: "Inundación reportada",
  floodRiskWarning: "Riesgo o alerta de inundación",
  heavyRainOnly: "Solo lluvia intensa",
  notFloodRelated: "No relacionado con inundaciones",
  uncertain: "No se puede determinar",
  legacyLabel: "Etiqueta anterior",
  classCount: "{count} etiquetas elegibles",
  cpuMinimum: "Mínimo para CPU",
  gpuMinimum: "Mínimo para GPU",
  smartReviewEyebrow: "Cierre la siguiente brecha de datos",
  smartReviewHeading: "Revise ahora las tarjetas de mayor valor.",
  smartReviewDescription: "Administración mantiene estables las tarjetas sin terminar, retira las completadas y rellena los espacios con selecciones respaldadas por el archivo que mejoran el equilibrio de etiquetas, fechas, editores, texto de inferencia o cobertura entre particiones.",
  smartReviewHint: "La cola nunca revela una etiqueta estimada. Su decisión independiente y basada en evidencia es la única respuesta guardada para el entrenamiento.",
  openSmartReviewQueue: "Abrir cola de revisión inteligente",
  eligibilityHeading: "Qué se puede usar hoy",
  eligibilityDescription: "Las revisiones excluidas se conservan para no borrar nada. Necesitan una corrección detallada antes de entrar al entrenamiento.",
  eligibleForTraining: "Elegibles para entrenamiento",
  excludedUncertain: "Excluidas: no se puede determinar",
  excludedLegacy: "Excluidas: esquema anterior",
  exclusionMismatch: "Otros registros excluidos",
  archiveFunnel: "Embudo de recopilación a entrenamiento",
  archiveFunnelHeading: "Más artículos recopilados no se convierten automáticamente en ejemplos de entrenamiento.",
  archiveFunnelDescription: "Cada etapa reduce el material. La revisión humana conecta el archivo permanente con una fila elegible para el modelo.",
  rawArchive: "Archivo GDELT bruto conservado",
  rawArchiveDetail: "{bytes} en {files} archivos comprimidos",
  permanentArticles: "Artículos archivados permanentemente",
  permanentArticlesHelp: "Registros de editores guardados y disponibles para muestreo",
  reviewedLabels: "Etiquetas revisadas más recientes",
  reviewedLabelsHelp: "Una decisión vigente por artículo revisado",
  eligibleRows: "Filas elegibles para entrenamiento",
  eligibleRowsHelp: "Solo etiquetas resueltas de versión 2",
  liveFunnelUnavailable: "El estado del archivo en vivo no está disponible temporalmente",
  dataFlow: "Flujo de datos",
  dataFlowHeading: "De una historia del editor a un experimento futuro.",
  dataFlowDescription: "Esta página sirve para inspeccionar y exportar. No inicia una tarea de entrenamiento.",
  flowReview: "Revisar el artículo",
  flowReviewHelp: "Una persona elige una etiqueta principal y puede añadir etiquetas de contexto.",
  flowLatest: "Conservar la última corrección",
  flowLatestHelp: "El registro sigue siendo de solo anexado; el conjunto usa la decisión más reciente por artículo.",
  flowEligibility: "Aplicar reglas de elegibilidad",
  flowEligibilityHelp: "Solo las cuatro clases resueltas de versión 2 entran al conjunto de entrenamiento.",
  flowExperiment: "Exportar, dividir y probar",
  flowExperimentHelp: "Una tarea futura debe crear periodos de entrenamiento, validación y reserva sin filtraciones antes del ajuste.",
  creditHeading: "Qué consume créditos",
  creditLocal: "Leer esta página y ejecutar entrenamiento futuro localmente en esta PC no consume créditos de ChatGPT. El cómputo local sí usa electricidad.",
  creditCodex: "El trabajo que le pida a Codex sí consume su asignación de Codex o ChatGPT. Una GPU en la nube tendría un costo separado.",
  datasetExplorer: "Explorador del conjunto",
  datasetExplorerHeading: "Inspeccione las filas detrás de los totales.",
  datasetExplorerDescription: "Busque y filtre localmente. La descarga CSV siempre exporta el conjunto completo de etiquetas vigentes desde la API.",
  search: "Buscar artículos",
  searchPlaceholder: "Título, editor, ID o etiqueta de contexto",
  labelFilter: "Etiqueta principal",
  eligibilityFilter: "Elegibilidad",
  allLabels: "Todas las etiquetas",
  allRows: "Todas las filas",
  eligibleOnly: "Solo elegibles",
  excludedOnly: "Solo excluidas",
  clearFilters: "Limpiar filtros",
  resultsCount: "Mostrando {visible} de {total} filas",
  easternTime: "Las horas de revisión usan la hora del este de EE. UU.",
  articleColumn: "Artículo",
  publisherColumn: "Editor",
  labelColumn: "Etiqueta principal",
  tagsColumn: "Etiquetas de contexto",
  reviewedColumn: "Revisado",
  eligibilityColumn: "Elegibilidad para entrenamiento",
  articleTableCaption: "Etiquetas de artículos más recientes y elegibilidad para entrenamiento",
  noTitle: "Artículo sin título",
  unknownPublisher: "Editor desconocido",
  noTags: "Sin etiquetas de contexto",
  eligible: "Elegible",
  excluded: "Excluida",
  legacyReason: "Necesita una corrección detallada de versión 2",
  uncertainReason: "No se puede determinar se conserva, pero se excluye",
  otherExclusionReason: "Excluida por las reglas actuales del conjunto",
  openPublisherStory: "Abrir historia del editor: {title}",
  loadingHeading: "Cargando el conjunto local de entrenamiento…",
  loadingHelp: "CrisisPulse está comprobando las etiquetas de artículos guardadas más recientemente.",
  errorHeading: "No se pudo cargar el conjunto de entrenamiento.",
  errorHelp: "Asegúrese de que la API local de CrisisPulse esté funcionando e inténtelo de nuevo. No se modificó ningún dato.",
  retry: "Intentar de nuevo",
  emptyHeading: "Todavía no hay artículos revisados.",
  emptyHelp: "Complete revisiones de artículos en Administración. Las filas elegibles y excluidas aparecerán aquí después de guardarlas.",
  filteredEmptyHeading: "Ninguna fila coincide con estos filtros.",
  filteredEmptyHelp: "Cambie la búsqueda o limpie los filtros para ver todo el conjunto.",
  lastLoaded: "Última comprobación: {time}",
  safeReadOnly: "Vista de datos de solo lectura",
  safeReadOnlyHelp: "Esta página no puede borrar revisiones, cambiar etiquetas, iniciar entrenamiento ni modificar alertas.",
});

type ResolvedDecision =
  | "reported_flooding"
  | "flood_risk_warning"
  | "heavy_rain_only"
  | "not_flood_related";

type TrainingArticle = {
  article_id: string;
  title: string;
  url: string;
  source_domain: string;
  match_strength: string;
  review_bucket: string;
  decision: string;
  decision_schema_version: number;
  tags?: string[];
  reviewed_at: string;
  training_eligible: boolean;
  exclusion_reason: string;
};

type TrainingDataset = {
  schema_version: number;
  summary: {
    total_articles: number;
    latest_reviewed_at?: string;
    training_eligible: number;
    excluded: number;
    class_counts: Record<ResolvedDecision, number>;
    exclusion_reason_counts: {
      legacy_schema: number;
      uncertain: number;
    };
  };
  articles: TrainingArticle[];
};

type TrainingAdminStatus = {
  refresh: {
    retained_raw_files: number;
    retained_raw_bytes?: number;
    archived_articles?: number;
  };
};

type TrainingAttemptStatus =
  | "not_ready"
  | "ready_for_cpu_baseline"
  | "ready_for_non_evaluative_smoke_test"
  | "blocked_cpu_baseline"
  | "blocked_non_evaluative_smoke_test"
  | "offline_cpu_baseline_completed"
  | "non_evaluative_smoke_test_completed";

type TrainingAttemptGate = {
  name: string;
  actual: number | boolean;
  minimum: number | boolean;
  passed: boolean;
};

type TrainingAttemptReadiness = {
  ready: boolean;
  gates: TrainingAttemptGate[];
};

type TrainingMapLocation = {
  location_name: string;
  country_code: string;
  latitude: number;
  longitude: number;
  article_count: number;
  class_counts: Record<ResolvedDecision, number>;
};

type TrainingGeographySummary = {
  meaning: "article_mentioned_locations_not_verified_events";
  source: "gdelt_primary_location_from_permanent_article_archive";
  usable_rows: number;
  mappable_rows: number;
  unmappable_rows: number;
  unique_locations: number;
  locations_returned: number;
  truncated: boolean;
  locations: TrainingMapLocation[];
};

type TrainingAttempt = {
  report_schema_version: number;
  dataset_fingerprint: string;
  status: TrainingAttemptStatus;
  training_performed: boolean;
  evaluation_tier?: "PRELIMINARY_OFFLINE_BASELINE" | "NON_EVALUATIVE_SMOKE_TEST";
  created_at: string;
  latest_review_count: number;
  latest_reviewed_at?: string;
  resolved_schema_v2_count: number;
  usable_training_rows: number;
  geography_summary?: TrainingGeographySummary;
  exclusion_counts: Record<string, number>;
  class_counts_before_text_filter: Record<ResolvedDecision, number>;
  class_counts_after_text_filter: Record<ResolvedDecision, number>;
  split: {
    computable: boolean;
    reason?: string;
    method?: string;
    time_field?: string;
    validation_boundary?: string;
    test_boundary?: string;
    story_rows_promoted_to_newer_split: number;
    earlier_rows_purged_for_final_publishers: number;
    story_overlap_after_purge: boolean;
    final_publisher_overlap_after_purge: boolean;
    training_rows: number;
    validation_rows: number;
    test_rows: number;
    class_counts: Record<string, Record<ResolvedDecision, number>>;
  };
  production_readiness: TrainingAttemptReadiness;
  smoke_test_readiness: TrainingAttemptReadiness;
  blocked_reason?: string;
};

type TrainingAttemptRequestState = "checking" | "refreshing" | "ready" | "missing" | "unavailable" | "stale";
type TrainingAttemptFetchResult =
  | { kind: "ready"; data: TrainingAttempt }
  | { kind: "missing" }
  | { kind: "unavailable" };

type LabelFilter = "all" | ResolvedDecision | "uncertain" | "legacy";
type EligibilityFilter = "all" | "eligible" | "excluded";
type RequestStatus = "loading" | "refreshing" | "ready" | "error";
type GateAuditStatus = "met" | "pending" | "unknown";
type GateAudit = {
  label: string;
  value: string;
  status: GateAuditStatus;
};
type MessageKey = keyof typeof messages.en;

const CPU_TOTAL_GATE = 500;
const CPU_CLASS_GATE = 100;
const GPU_TOTAL_GATE = 2_000;
const GPU_CLASS_GATE = 300;
const GPU_DAY_GATE = 60;
const GPU_PUBLISHER_GATE = 250;
const DOUBLE_REVIEW_GATE = 200;
const AGREEMENT_GATE = 0.75;
const AVAILABILITY_GATE = 95;
const trainingDatasetURL = "/api/v1/training/articles";
const trainingCSVURL = "/api/v1/training/articles/export.csv";
const adminStatusURL = "/api/v1/admin/status";
const trainingStatusURL = "/api/v1/training/status";
const naturalEarthMapURL = "/data/ne_110m_admin_0_countries.geojson";

const trainingAttemptStatuses = new Set<TrainingAttemptStatus>([
  "not_ready",
  "ready_for_cpu_baseline",
  "ready_for_non_evaluative_smoke_test",
  "blocked_cpu_baseline",
  "blocked_non_evaluative_smoke_test",
  "offline_cpu_baseline_completed",
  "non_evaluative_smoke_test_completed",
]);

const completedTrainingAttemptStatuses = new Set<TrainingAttemptStatus>([
  "offline_cpu_baseline_completed",
  "non_evaluative_smoke_test_completed",
]);

const resolvedClasses: Array<{
  value: ResolvedDecision;
  labelKey: MessageKey;
  tone: string;
}> = [
  { value: "reported_flooding", labelKey: "reportedFlooding", tone: "reported" },
  { value: "flood_risk_warning", labelKey: "floodRiskWarning", tone: "risk" },
  { value: "heavy_rain_only", labelKey: "heavyRainOnly", tone: "rain" },
  { value: "not_flood_related", labelKey: "notFloodRelated", tone: "unrelated" },
];

const trainingGateLabelKeys: Record<string, MessageKey> = {
  total_usable_rows: "gateTotalUsableRows",
  minimum_rows_in_each_class: "gateMinimumClass",
  distinct_article_dates: "gateDistinctDates",
  publisher_groups: "gatePublisherGroups",
  inference_text_coverage: "gateInferenceCoverage",
  training_rows_in_each_class_after_purge: "gateTrainingClass",
  validation_rows_in_each_class_after_purge: "gateValidationClass",
  test_rows_in_each_class_after_purge: "gateTestClass",
  leakage_safe_split_computable: "gateSplitComputable",
};

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === "object" && value !== null
);

const isTrainingDataset = (value: unknown): value is TrainingDataset => {
  if (!isRecord(value) || !isRecord(value.summary) || !Array.isArray(value.articles)) return false;
  const summary = value.summary;
  return typeof value.schema_version === "number"
    && typeof summary.total_articles === "number"
    && (summary.latest_reviewed_at === undefined
      || (typeof summary.latest_reviewed_at === "string" && !Number.isNaN(Date.parse(summary.latest_reviewed_at))))
    && typeof summary.training_eligible === "number"
    && typeof summary.excluded === "number"
    && isRecord(summary.class_counts)
    && isRecord(summary.exclusion_reason_counts);
};

const isTrainingAdminStatus = (value: unknown): value is TrainingAdminStatus => (
  isRecord(value)
  && isRecord(value.refresh)
  && typeof value.refresh.retained_raw_files === "number"
);

const trainingGateNames = new Set([
  "total_usable_rows",
  "minimum_rows_in_each_class",
  "distinct_article_dates",
  "publisher_groups",
  "inference_text_coverage",
  "training_rows_in_each_class_after_purge",
  "validation_rows_in_each_class_after_purge",
  "test_rows_in_each_class_after_purge",
  "leakage_safe_split_computable",
]);

const isNonNegativeInteger = (value: unknown): value is number => (
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0
);

const isCountRecord = (value: unknown): value is Record<string, number> => (
  isRecord(value)
  && Object.values(value).every(isNonNegativeInteger)
);

const isResolvedClassCounts = (value: unknown): value is Record<ResolvedDecision, number> => (
  isCountRecord(value)
  && Object.keys(value).length === resolvedClasses.length
  && resolvedClasses.every(({ value: decision }) => isNonNegativeInteger(value[decision]))
);

const isTrainingAttemptGate = (value: unknown): value is TrainingAttemptGate => {
  if (!isRecord(value) || typeof value.name !== "string" || !trainingGateNames.has(value.name)) return false;
  const actualIsValid = typeof value.actual === "boolean"
    || (typeof value.actual === "number" && Number.isFinite(value.actual) && value.actual >= 0);
  const minimumIsValid = typeof value.minimum === "boolean"
    || (typeof value.minimum === "number" && Number.isFinite(value.minimum) && value.minimum >= 0);
  return actualIsValid
    && minimumIsValid
    && typeof value.actual === typeof value.minimum
    && typeof value.passed === "boolean";
};

const isTrainingAttemptReadiness = (value: unknown): value is TrainingAttemptReadiness => {
  if (!isRecord(value)
    || typeof value.ready !== "boolean"
    || !Array.isArray(value.gates)
    || !value.gates.every(isTrainingAttemptGate)) return false;
  return new Set(value.gates.map((gate) => gate.name)).size === value.gates.length;
};

const isTrainingGeographySummary = (value: unknown): value is TrainingGeographySummary => {
  if (!isRecord(value)
    || value.meaning !== "article_mentioned_locations_not_verified_events"
    || value.source !== "gdelt_primary_location_from_permanent_article_archive"
    || !isNonNegativeInteger(value.usable_rows)
    || !isNonNegativeInteger(value.mappable_rows)
    || !isNonNegativeInteger(value.unmappable_rows)
    || value.mappable_rows + value.unmappable_rows !== value.usable_rows
    || !isNonNegativeInteger(value.unique_locations)
    || !isNonNegativeInteger(value.locations_returned)
    || typeof value.truncated !== "boolean"
    || !Array.isArray(value.locations)
    || value.locations_returned !== value.locations.length
    || value.locations.length > 250
    || value.unique_locations < value.locations.length) return false;
  let returnedRows = 0;
  const locationsAreValid = value.locations.every((location) => {
    if (!isRecord(location)
      || typeof location.location_name !== "string"
      || !location.location_name.trim()
      || location.location_name !== location.location_name.trim()
      || typeof location.country_code !== "string"
      || typeof location.latitude !== "number"
      || !Number.isFinite(location.latitude)
      || location.latitude < -90
      || location.latitude > 90
      || typeof location.longitude !== "number"
      || !Number.isFinite(location.longitude)
      || location.longitude < -180
      || location.longitude > 180
      || !isNonNegativeInteger(location.article_count)
      || location.article_count === 0
      || !isResolvedClassCounts(location.class_counts)) return false;
    const classTotal = Object.values(location.class_counts).reduce((total, count) => total + count, 0);
    if (classTotal !== location.article_count) return false;
    returnedRows += location.article_count;
    return true;
  });
  if (!locationsAreValid || returnedRows > value.mappable_rows) return false;
  return value.truncated
    ? value.unique_locations > value.locations.length
    : value.unique_locations === value.locations.length && returnedRows === value.mappable_rows;
};

const isTrainingAttemptSplit = (value: unknown): value is TrainingAttempt["split"] => {
  if (!isRecord(value)
    || typeof value.computable !== "boolean"
    || !isNonNegativeInteger(value.story_rows_promoted_to_newer_split)
    || !isNonNegativeInteger(value.earlier_rows_purged_for_final_publishers)
    || typeof value.story_overlap_after_purge !== "boolean"
    || typeof value.final_publisher_overlap_after_purge !== "boolean"
    || !isNonNegativeInteger(value.training_rows)
    || !isNonNegativeInteger(value.validation_rows)
    || !isNonNegativeInteger(value.test_rows)
    || !isRecord(value.class_counts)) return false;
  if ([value.reason, value.method, value.time_field, value.validation_boundary, value.test_boundary]
    .some((item) => item !== undefined && typeof item !== "string")) return false;
  const splitNames = Object.keys(value.class_counts);
  if (!value.computable) return splitNames.length === 0;
  return splitNames.length === 3
    && ["training", "validation", "test"].every((name) => isResolvedClassCounts(value.class_counts[name]));
};

const isTrainingAttempt = (value: unknown): value is TrainingAttempt => {
  if (!isRecord(value)
    || (value.report_schema_version !== 1 && value.report_schema_version !== 2)
    || typeof value.dataset_fingerprint !== "string"
    || !/^sha256:[a-f0-9]{64}$/.test(value.dataset_fingerprint)
    || typeof value.status !== "string"
    || !trainingAttemptStatuses.has(value.status as TrainingAttemptStatus)
    || typeof value.training_performed !== "boolean"
    || typeof value.created_at !== "string"
    || Number.isNaN(Date.parse(value.created_at))
    || !isNonNegativeInteger(value.latest_review_count)
    || !isNonNegativeInteger(value.resolved_schema_v2_count)
    || !isNonNegativeInteger(value.usable_training_rows)
    || !isCountRecord(value.exclusion_counts)
    || !isResolvedClassCounts(value.class_counts_before_text_filter)
    || !isResolvedClassCounts(value.class_counts_after_text_filter)
    || !isTrainingAttemptSplit(value.split)
    || !isTrainingAttemptReadiness(value.production_readiness)
    || !isTrainingAttemptReadiness(value.smoke_test_readiness)) return false;
  if (value.geography_summary !== undefined && !isTrainingGeographySummary(value.geography_summary)) return false;
  if (value.latest_reviewed_at !== undefined
    && (typeof value.latest_reviewed_at !== "string" || Number.isNaN(Date.parse(value.latest_reviewed_at)))) return false;
  if (value.report_schema_version === 2
    && (value.latest_reviewed_at === undefined || value.geography_summary === undefined)) return false;
  if (value.report_schema_version === 1
    && (value.latest_reviewed_at !== undefined || value.geography_summary !== undefined)) return false;
  if (value.evaluation_tier !== undefined
    && value.evaluation_tier !== "PRELIMINARY_OFFLINE_BASELINE"
    && value.evaluation_tier !== "NON_EVALUATIVE_SMOKE_TEST") return false;
  if (value.blocked_reason !== undefined && typeof value.blocked_reason !== "string") return false;

  const candidate = value as TrainingAttempt;
  const sumCounts = (counts: Record<string, number>) => (
    Object.values(counts).reduce((total, count) => total + count, 0)
  );
  if (candidate.resolved_schema_v2_count > candidate.latest_review_count
    || candidate.usable_training_rows > candidate.resolved_schema_v2_count
    || sumCounts(candidate.class_counts_before_text_filter) !== candidate.resolved_schema_v2_count
    || sumCounts(candidate.class_counts_after_text_filter) !== candidate.usable_training_rows
    || sumCounts(candidate.exclusion_counts) + candidate.usable_training_rows !== candidate.latest_review_count) return false;
  if (candidate.geography_summary && candidate.geography_summary.usable_rows !== candidate.usable_training_rows) return false;
  if (candidate.split.computable) {
    if (candidate.split.training_rows + candidate.split.validation_rows + candidate.split.test_rows
      + candidate.split.earlier_rows_purged_for_final_publishers !== candidate.usable_training_rows) return false;
    for (const [name, rows] of [["training", candidate.split.training_rows], ["validation", candidate.split.validation_rows], ["test", candidate.split.test_rows]] as const) {
      if (sumCounts(candidate.split.class_counts[name]) !== rows) return false;
    }
  }
  const completed = completedTrainingAttemptStatuses.has(candidate.status);
  if (candidate.training_performed !== completed) return false;
  if (candidate.training_performed !== Boolean(candidate.evaluation_tier)) return false;
  return true;
};

const fetchTrainingAttempt = async (signal: AbortSignal): Promise<TrainingAttemptFetchResult> => {
  try {
    const response = await fetch(trainingStatusURL, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal,
    });
    if (response.status === 404) return { kind: "missing" };
    if (!response.ok) return { kind: "unavailable" };
    const payload: unknown = await response.json();
    return isTrainingAttempt(payload) ? { kind: "ready", data: payload } : { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
};

const safeArticleURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
};

const clampPercent = (current: number, target: number) => (
  Math.min(100, Math.max(0, (current / target) * 100))
);

const classMinimumMet = (
  counts: Record<ResolvedDecision, number>,
  minimum: number,
) => resolvedClasses.every(({ value }) => counts[value] >= minimum);

const labelTone = (decision: string) => {
  const resolvedClass = resolvedClasses.find(({ value }) => value === decision);
  if (resolvedClass) return resolvedClass.tone;
  if (decision === "mixed") return "mixed";
  if (decision === "uncertain") return "uncertain";
  return "legacy";
};

type WorldMapState = "idle" | "loading" | "ready" | "error";

const projectMapPosition = (longitude: number, latitude: number) => ({
  x: ((longitude + 180) / 360) * 960,
  y: ((90 - latitude) / 180) * 480,
});

const isGeoPosition = (value: unknown): value is [number, number] => (
  Array.isArray(value)
  && value.length >= 2
  && typeof value[0] === "number"
  && Number.isFinite(value[0])
  && value[0] >= -180
  && value[0] <= 180
  && typeof value[1] === "number"
  && Number.isFinite(value[1])
  && value[1] >= -90
  && value[1] <= 90
);

const worldRingPath = (value: unknown): string | null => {
  if (!Array.isArray(value) || value.length < 4 || !value.every(isGeoPosition)) return null;
  const commands = value.map(([longitude, latitude], index) => {
    const { x, y } = projectMapPosition(longitude, latitude);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return `${commands.join("")}Z`;
};

const worldPolygonPath = (value: unknown): string | null => {
  if (!Array.isArray(value)) return null;
  const rings = value.map(worldRingPath);
  return rings.every((ring): ring is string => Boolean(ring)) ? rings.join("") : null;
};

const worldPathsFromGeoJSON = (value: unknown): string[] | null => {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features) || value.features.length > 400) return null;
  const paths: string[] = [];
  for (const feature of value.features) {
    if (!isRecord(feature) || !isRecord(feature.geometry) || typeof feature.geometry.type !== "string") return null;
    if (feature.geometry.type === "Polygon") {
      const path = worldPolygonPath(feature.geometry.coordinates);
      if (!path) return null;
      paths.push(path);
      continue;
    }
    if (feature.geometry.type === "MultiPolygon" && Array.isArray(feature.geometry.coordinates)) {
      for (const polygon of feature.geometry.coordinates) {
        const path = worldPolygonPath(polygon);
        if (!path) return null;
        paths.push(path);
      }
      continue;
    }
    return null;
  }
  return paths.length ? paths : null;
};

type LocationTone = ResolvedDecision | "mixed";

const dominantLocationDecision = (location: TrainingMapLocation): LocationTone => {
  const maximum = Math.max(...resolvedClasses.map(({ value }) => location.class_counts[value]));
  const leaders = resolvedClasses.filter(({ value }) => location.class_counts[value] === maximum);
  return leaders.length === 1 ? leaders[0].value : "mixed";
};

export default function TrainingDataPage() {
  const { locale, localeTag } = useLocale();
  const pageMessages = messages[locale];
  const t = useCallback((key: MessageKey, values: Record<string, string | number> = {}) => (
    formatMessage(pageMessages[key], values)
  ), [pageMessages]);
  const [dataset, setDataset] = useState<TrainingDataset | null>(null);
  const [adminStatus, setAdminStatus] = useState<TrainingAdminStatus | null>(null);
  const [adminStatusChecked, setAdminStatusChecked] = useState(false);
  const [trainingAttempt, setTrainingAttempt] = useState<TrainingAttempt | null>(null);
  const trainingAttemptRef = useRef<TrainingAttempt | null>(null);
  const [trainingAttemptState, setTrainingAttemptState] = useState<TrainingAttemptRequestState>("checking");
  const [requestStatus, setRequestStatus] = useState<RequestStatus>("loading");
  const [requestError, setRequestError] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [search, setSearch] = useState("");
  const [labelFilter, setLabelFilter] = useState<LabelFilter>("all");
  const [eligibilityFilter, setEligibilityFilter] = useState<EligibilityFilter>("all");
  const [worldMapState, setWorldMapState] = useState<WorldMapState>("idle");
  const [worldPaths, setWorldPaths] = useState<string[]>([]);
  const [selectedMapLocation, setSelectedMapLocation] = useState<TrainingMapLocation | null>(null);

  useEffect(() => {
    document.title = pageMessages.documentTitle;
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement("meta");
      description.name = "description";
      document.head.appendChild(description);
    }
    description.content = pageMessages.documentDescription;
  }, [pageMessages.documentDescription, pageMessages.documentTitle]);

  const loadDataset = useCallback(async (parentSignal?: AbortSignal) => {
    setRequestStatus((current) => current === "ready" ? "refreshing" : "loading");
    setRequestError(false);
    setTrainingAttemptState(trainingAttemptRef.current ? "refreshing" : "checking");
    const controller = new AbortController();
    const abortFromParent = () => controller.abort();
    if (parentSignal?.aborted) controller.abort();
    else parentSignal?.addEventListener("abort", abortFromParent, { once: true });
    const timeout = window.setTimeout(() => controller.abort(), 8_000);
    try {
      setAdminStatusChecked(false);
      const [response, statusPayload, attemptResult] = await Promise.all([
        fetch(trainingDatasetURL, {
          cache: "no-store",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        }),
        fetch(adminStatusURL, {
          cache: "no-store",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        }).then(async (statusResponse): Promise<unknown> => (
          statusResponse.ok ? statusResponse.json() : null
        )).catch(() => null),
        fetchTrainingAttempt(controller.signal),
      ]);
      if (!response.ok) throw new Error("training dataset request failed");
      const payload: unknown = await response.json();
      if (!isTrainingDataset(payload)) throw new Error("unexpected training dataset response");
      setDataset(payload);
      setAdminStatus(isTrainingAdminStatus(statusPayload) ? statusPayload : null);
      if (attemptResult.kind === "ready") {
        trainingAttemptRef.current = attemptResult.data;
        setTrainingAttempt(attemptResult.data);
        setTrainingAttemptState("ready");
      } else if (attemptResult.kind === "missing") {
        trainingAttemptRef.current = null;
        setTrainingAttempt(null);
        setTrainingAttemptState("missing");
      } else {
        setTrainingAttemptState(trainingAttemptRef.current ? "stale" : "unavailable");
      }
      setAdminStatusChecked(true);
      setLastLoadedAt(new Date());
      setRequestStatus("ready");
    } catch {
      if (controller.signal.aborted && parentSignal?.aborted) return;
      setRequestError(true);
      setAdminStatusChecked(true);
      setTrainingAttemptState(trainingAttemptRef.current ? "stale" : "unavailable");
      setRequestStatus((current) => current === "refreshing" ? "ready" : "error");
    } finally {
      window.clearTimeout(timeout);
      parentSignal?.removeEventListener("abort", abortFromParent);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void loadDataset(controller.signal), 0);
    return () => {
      window.clearTimeout(initialLoad);
      controller.abort();
    };
  }, [loadDataset]);

  useEffect(() => {
    const hasLocations = Boolean(trainingAttempt?.geography_summary?.locations.length);
    const controller = new AbortController();
    const initializeMap = window.setTimeout(() => {
      setSelectedMapLocation(null);
      if (!hasLocations) {
        setWorldMapState("idle");
        setWorldPaths([]);
        return;
      }
      setWorldMapState("loading");
      fetch(naturalEarthMapURL, {
        cache: "force-cache",
        headers: { Accept: "application/geo+json, application/json" },
        signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok) throw new Error("world boundaries unavailable");
        const payload: unknown = await response.json();
        const paths = worldPathsFromGeoJSON(payload);
        if (!paths) throw new Error("invalid world boundaries");
        setWorldPaths(paths);
        setWorldMapState("ready");
      }).catch(() => {
        if (!controller.signal.aborted) {
          setWorldPaths([]);
          setWorldMapState("error");
        }
      });
    }, 0);
    return () => {
      window.clearTimeout(initializeMap);
      controller.abort();
    };
  }, [trainingAttempt?.dataset_fingerprint, trainingAttempt?.geography_summary?.locations.length]);

  const formatNumber = useCallback((value: number) => value.toLocaleString(localeTag), [localeTag]);
  const formatBytes = useCallback((value: number | null | undefined) => {
    if (value === null || value === undefined || value < 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let amount = value;
    let unitIndex = 0;
    while (amount >= 1_000 && unitIndex < units.length - 1) {
      amount /= 1_000;
      unitIndex += 1;
    }
    return `${new Intl.NumberFormat(localeTag, {
      maximumFractionDigits: unitIndex === 0 ? 0 : 1,
    }).format(amount)} ${units[unitIndex]}`;
  }, [localeTag]);
  const formatEastern = useCallback((value: string | Date) => {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString(localeTag, {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  }, [localeTag]);

  const decisionLabel = useCallback((article: TrainingArticle) => {
    const resolvedClass = resolvedClasses.find(({ value }) => value === article.decision);
    if (resolvedClass) return t(resolvedClass.labelKey);
    if (article.decision === "uncertain") return t("uncertain");
    return t("legacyLabel");
  }, [t]);

  const exclusionLabel = useCallback((article: TrainingArticle) => {
    if (article.training_eligible) return t("eligible");
    if (article.exclusion_reason === "legacy_schema") return t("legacyReason");
    if (article.exclusion_reason === "uncertain") return t("uncertainReason");
    return t("otherExclusionReason");
  }, [t]);

  const formatAttemptGateValue = useCallback((gate: TrainingAttemptGate, value: number | boolean) => {
    if (typeof value === "boolean") return t(value ? "attemptGateYes" : "attemptGateNo");
    if (gate.name === "inference_text_coverage") {
      return new Intl.NumberFormat(localeTag, { style: "percent", maximumFractionDigits: 1 }).format(value);
    }
    return new Intl.NumberFormat(localeTag, { maximumFractionDigits: 1 }).format(value);
  }, [localeTag, t]);

  const visibleArticles = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase(localeTag);
    return (dataset?.articles ?? []).filter((article) => {
      const matchesSearch = !normalizedSearch || [
        article.title,
        article.source_domain,
        article.article_id,
        ...(article.tags ?? []),
      ].some((value) => value.toLocaleLowerCase(localeTag).includes(normalizedSearch));
      const isLegacy = article.decision_schema_version !== 2 || article.exclusion_reason === "legacy_schema";
      const matchesLabel = labelFilter === "all"
        || (labelFilter === "legacy" ? isLegacy : article.decision === labelFilter);
      const matchesEligibility = eligibilityFilter === "all"
        || (eligibilityFilter === "eligible" ? article.training_eligible : !article.training_eligible);
      return matchesSearch && matchesLabel && matchesEligibility;
    });
  }, [dataset?.articles, eligibilityFilter, labelFilter, localeTag, search]);

  const summary = dataset?.summary;
  const classCounts = summary?.class_counts ?? {
    reported_flooding: 0,
    flood_risk_warning: 0,
    heavy_rain_only: 0,
    not_flood_related: 0,
  };
  const smallestClassCount = Math.min(...resolvedClasses.map(({ value }) => classCounts[value]));
  const eligibleCount = summary?.training_eligible ?? 0;
  const productionGateByName = new Map(
    (trainingAttempt?.production_readiness.gates ?? []).map((gate) => [gate.name, gate]),
  );
  const attemptGateAudit = (name: string, label: string): GateAudit => {
    const gate = productionGateByName.get(name);
    return gate ? {
      label,
      value: t("attemptGateValue", {
        actual: formatAttemptGateValue(gate, gate.actual),
        minimum: formatAttemptGateValue(gate, gate.minimum),
      }),
      status: gate.passed ? "met" : "pending",
    } : { label, value: t("notComputable"), status: "unknown" };
  };
  const splitAttemptGates = [
    productionGateByName.get("training_rows_in_each_class_after_purge"),
    productionGateByName.get("validation_rows_in_each_class_after_purge"),
    productionGateByName.get("test_rows_in_each_class_after_purge"),
  ];
  const splitAudit: GateAudit = splitAttemptGates.every((gate): gate is TrainingAttemptGate => Boolean(gate))
    ? {
        label: t("splitViabilityRequirement"),
        value: t("splitGateValue", {
          training: formatAttemptGateValue(splitAttemptGates[0], splitAttemptGates[0].actual),
          validation: formatAttemptGateValue(splitAttemptGates[1], splitAttemptGates[1].actual),
          test: formatAttemptGateValue(splitAttemptGates[2], splitAttemptGates[2].actual),
        }),
        status: splitAttemptGates.every((gate) => gate?.passed) ? "met" : "pending",
      }
    : {
        label: t("splitViabilityRequirement"),
        value: t("notComputable"),
        status: "unknown",
      };
  const cpuAudits: GateAudit[] = [
    {
      label: t("eligibleLabelRequirement"),
      value: t("countRequirement", { current: formatNumber(eligibleCount), target: formatNumber(CPU_TOTAL_GATE) }),
      status: eligibleCount >= CPU_TOTAL_GATE ? "met" : "pending",
    },
    {
      label: t("classMinimumRequirement"),
      value: t("countRequirement", { current: formatNumber(smallestClassCount), target: formatNumber(CPU_CLASS_GATE) }),
      status: classMinimumMet(classCounts, CPU_CLASS_GATE) ? "met" : "pending",
    },
    attemptGateAudit("distinct_article_dates", t("articleDaysRequirement")),
    attemptGateAudit("publisher_groups", t("publisherRequirement")),
    attemptGateAudit("inference_text_coverage", t("inferenceTextRequirement")),
    splitAudit,
    {
      label: t("baselineEvidenceRequirement"),
      value: `${t("notComputable")} · ${t("baselineEvidenceTarget")}`,
      status: "unknown",
    },
  ];
  const gpuAudits: GateAudit[] = [
    {
      label: t("eligibleLabelRequirement"),
      value: t("countRequirement", { current: formatNumber(eligibleCount), target: formatNumber(GPU_TOTAL_GATE) }),
      status: eligibleCount >= GPU_TOTAL_GATE ? "met" : "pending",
    },
    {
      label: t("classMinimumRequirement"),
      value: t("countRequirement", { current: formatNumber(smallestClassCount), target: formatNumber(GPU_CLASS_GATE) }),
      status: classMinimumMet(classCounts, GPU_CLASS_GATE) ? "met" : "pending",
    },
    {
      label: t("articleDaysRequirement"),
      value: `${t("notComputable")} · ${formatNumber(GPU_DAY_GATE)}`,
      status: "unknown",
    },
    {
      label: t("publisherRequirement"),
      value: `${t("notComputable")} · ${formatNumber(GPU_PUBLISHER_GATE)}`,
      status: "unknown",
    },
    {
      label: t("featureParityRequirement"),
      value: `${t("notComputable")} · ${t("percentageRequirement", { target: AVAILABILITY_GATE })}`,
      status: "unknown",
    },
    {
      label: t("splitViabilityRequirement"),
      value: t("notComputable"),
      status: "unknown",
    },
    {
      label: t("doubleReviewRequirement"),
      value: `${t("notComputable")} · ${formatNumber(DOUBLE_REVIEW_GATE)}`,
      status: "unknown",
    },
    {
      label: t("kappaRequirement"),
      value: `${t("notComputable")} · ≥ ${AGREEMENT_GATE.toLocaleString(localeTag)}`,
      status: "unknown",
    },
    {
      label: t("cpuBaselineRequirement"),
      value: `${t("notComputable")} · ${t("cpuBaselinePending")}`,
      status: "unknown",
    },
  ];
  const gateStatusLabel = (status: GateAuditStatus) => (
    status === "met" ? t("requirementMet") : status === "pending" ? t("requirementPending") : t("notComputable")
  );
  const otherExcluded = summary
    ? Math.max(0, summary.excluded
      - summary.exclusion_reason_counts.legacy_schema
      - summary.exclusion_reason_counts.uncertain)
    : 0;
  const hasFilters = Boolean(search || labelFilter !== "all" || eligibilityFilter !== "all");

  const attemptIsSmokeTest = Boolean(trainingAttempt && [
    "ready_for_non_evaluative_smoke_test",
    "blocked_non_evaluative_smoke_test",
    "non_evaluative_smoke_test_completed",
  ].includes(trainingAttempt.status));
  const attemptReadiness = trainingAttempt
    ? attemptIsSmokeTest ? trainingAttempt.smoke_test_readiness : trainingAttempt.production_readiness
    : null;
  const attemptExcludedCount = trainingAttempt
    ? Object.values(trainingAttempt.exclusion_counts).reduce((total, count) => total + count, 0)
    : 0;
  const attemptTone = trainingAttempt?.training_performed
    ? "complete"
    : trainingAttempt?.status.startsWith("ready_for_")
      ? "ready"
      : "blocked";
  const attemptStatusHeading = trainingAttempt?.training_performed
    ? t("attemptCompleted")
    : trainingAttempt?.status.startsWith("ready_for_")
      ? t("attemptReady")
      : trainingAttempt?.status.startsWith("blocked_")
        ? t("attemptStopped")
        : t("attemptReadinessOnly");
  const attemptStatusHelp = trainingAttempt?.training_performed
    ? t("attemptCompletedHelp")
    : trainingAttempt?.status.startsWith("ready_for_")
      ? t("attemptReadyHelp")
      : t("attemptWhyStopped");
  const currentClassMaximum = Math.max(1, ...resolvedClasses.map(({ value }) => classCounts[value]));
  const splitPeriods = [
    { value: "training", label: t("attemptTrainingRows") },
    { value: "validation", label: t("attemptValidationRows") },
    { value: "test", label: t("attemptTestRows") },
  ] as const;
  const splitClassMaximum = trainingAttempt?.split.computable
    ? Math.max(1, ...splitPeriods.flatMap(({ value }) => (
        resolvedClasses.map((classDefinition) => trainingAttempt.split.class_counts[value][classDefinition.value])
      )))
    : 1;
  const splitGapLabels = trainingAttempt?.split.computable
    ? resolvedClasses
        .filter(({ value }) => (
          trainingAttempt.split.class_counts.training[value] === 0
          || trainingAttempt.split.class_counts.validation[value] === 0
          || trainingAttempt.split.class_counts.test[value] === 0
        ))
        .map(({ labelKey }) => t(labelKey))
    : [];
  const attemptSnapshotDiffers = Boolean(
    trainingAttempt && summary && (
      trainingAttempt.latest_review_count !== summary.total_articles
      || trainingAttempt.resolved_schema_v2_count !== summary.training_eligible
      || (trainingAttempt.latest_reviewed_at !== undefined
        && summary.latest_reviewed_at !== undefined
        && Date.parse(trainingAttempt.latest_reviewed_at) !== Date.parse(summary.latest_reviewed_at))
      || resolvedClasses.some(({ value }) => (
        trainingAttempt.class_counts_before_text_filter[value] !== summary.class_counts[value]
      ))
    ),
  );
  const mapGeography = trainingAttempt?.geography_summary;
  const mapLocations = mapGeography?.locations ?? [];
  const returnedMappedRows = mapLocations.reduce((total, location) => total + location.article_count, 0);
  const listedMapLocations = mapLocations.slice(0, 12);

  const clearFilters = () => {
    setSearch("");
    setLabelFilter("all");
    setEligibilityFilter("all");
  };

  return (
    <main className="training-lab-page">
      <header className="site-header">
        <Link className="brand" href="/" aria-label={t("brandHome")}>
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </Link>
        <nav className="header-nav" aria-label={t("primaryNavigation")}>
          <Link href="/">{t("dashboard")}</Link>
          <Link href="/admin">{t("admin")}</Link>
          <Link aria-current="page" className="active" href="/admin/training-data">{t("trainingData")}</Link>
        </nav>
        <div className="header-meta" aria-live="polite">
          <span
            aria-hidden="true"
            className={requestStatus === "ready" || requestStatus === "refreshing" ? "live-dot" : "live-dot snapshot"}
          />
          <strong>
            {requestStatus === "loading"
              ? t("checkingLocalApi")
              : requestStatus === "error"
                ? t("localApiUnavailable")
                : t("liveFromLocalApi")}
          </strong>
        </div>
        <LanguageSwitcher />
      </header>

      <section className="tdl-hero" aria-labelledby="training-lab-heading">
        <div className="tdl-hero-copy">
          <p className="eyebrow">{t("localDataset")}</p>
          <h1 id="training-lab-heading">{t("heroTitle")}</h1>
          <p>{t("heroDescription")}</p>
          <div className="tdl-hero-actions">
            <button
              disabled={requestStatus === "loading" || requestStatus === "refreshing"}
              onClick={() => void loadDataset()}
              type="button"
            >
              {requestStatus === "refreshing" ? t("refreshing") : t("refresh")}
            </button>
            <a download="crisispulse-training-articles.csv" href={trainingCSVURL}>{t("exportCsv")}</a>
            <Link href="/admin/training-data/dataset-audit">{t("auditExternalData")}</Link>
          </div>
          {lastLoadedAt ? <small>{t("lastLoaded", { time: formatEastern(lastLoadedAt) })}</small> : null}
        </div>
        <aside className="tdl-hardware" aria-labelledby="hardware-heading">
          <p className="eyebrow">{t("hardwareHeading")}</p>
          <h2 id="hardware-heading">{t("gpuName")}</h2>
          <p>{t("hardwareHelp")}</p>
          <ul>
            <li>{t("gpuMemory")}</li>
            <li>{t("gpuCapability")}</li>
            <li>{t("cudaVersion")}</li>
          </ul>
          <strong className="ready"><span aria-hidden="true">✓</span> {t("cpuRunnerReady")}</strong>
          <p className="tdl-runner-help">{t("cpuRunnerHelp")}</p>
          <strong><span aria-hidden="true">!</span> {t("noGpuJob")}</strong>
        </aside>
      </section>

      {requestError && dataset ? (
        <div className="tdl-inline-error" role="alert">
          <strong>{t("errorHeading")}</strong>
          <span>{t("errorHelp")}</span>
          <button onClick={() => void loadDataset()} type="button">{t("retry")}</button>
        </div>
      ) : null}

      {requestStatus === "loading" ? (
        <section className="tdl-state" aria-busy="true" aria-live="polite">
          <span className="tdl-spinner" aria-hidden="true" />
          <div>
            <h2>{t("loadingHeading")}</h2>
            <p>{t("loadingHelp")}</p>
          </div>
        </section>
      ) : requestStatus === "error" && !dataset ? (
        <section className="tdl-state tdl-error-state" role="alert">
          <span aria-hidden="true">!</span>
          <div>
            <h2>{t("errorHeading")}</h2>
            <p>{t("errorHelp")}</p>
            <button onClick={() => void loadDataset()} type="button">{t("retry")}</button>
          </div>
        </section>
      ) : dataset ? (
        <>
          <section className="tdl-section tdl-attempt-section" aria-labelledby="training-attempt-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("trainingAttemptEyebrow")}</p>
                <h2 id="training-attempt-heading">{t("trainingAttemptHeading")}</h2>
                <p>{t("trainingAttemptDescription")}</p>
              </div>
            </div>

            {trainingAttemptState === "stale" ? (
              <p className="tdl-attempt-notice" role="status">{t("attemptStale")}</p>
            ) : null}

            {(trainingAttemptState === "checking" || trainingAttemptState === "refreshing") && !trainingAttempt ? (
              <div className="tdl-attempt-empty" aria-busy="true" aria-live="polite">
                <span className="tdl-spinner" aria-hidden="true" />
                <p>{t("attemptChecking")}</p>
              </div>
            ) : trainingAttemptState === "missing" ? (
              <div className="tdl-attempt-empty">
                <span aria-hidden="true">0</span>
                <div><h3>{t("attemptMissingHeading")}</h3><p>{t("attemptMissingHelp")}</p></div>
              </div>
            ) : trainingAttemptState === "unavailable" && !trainingAttempt ? (
              <div className="tdl-attempt-empty warning" role="status">
                <span aria-hidden="true">!</span>
                <div><h3>{t("attemptUnavailableHeading")}</h3><p>{t("attemptUnavailableHelp")}</p></div>
              </div>
            ) : trainingAttempt ? (
              <article className={`tdl-attempt-card ${attemptTone}`}>
                <header className="tdl-attempt-header">
                  <div>
                    <span className="tdl-attempt-status">{attemptStatusHeading}</span>
                    <h3>{trainingAttempt.training_performed ? t("modelCreated") : t("noModelCreated")}</h3>
                    <p>{attemptStatusHelp}</p>
                  </div>
                  <div className={`tdl-model-badge ${trainingAttempt.training_performed ? "created" : "not-created"}`}>
                    <span aria-hidden="true">{trainingAttempt.training_performed ? "✓" : "×"}</span>
                    <strong>{trainingAttempt.training_performed ? t("modelCreated") : t("noModelCreated")}</strong>
                    <time dateTime={trainingAttempt.created_at}>{t("attemptSaved", { time: formatEastern(trainingAttempt.created_at) })}</time>
                  </div>
                </header>

                <section className="tdl-attempt-block" aria-labelledby="attempt-counts-heading">
                  <h4 id="attempt-counts-heading">{t("attemptCountsHeading")}</h4>
                  <dl className="tdl-attempt-counts">
                    <div><dt>{t("attemptLatestReviews")}</dt><dd>{formatNumber(trainingAttempt.latest_review_count)}</dd></div>
                    <div><dt>{t("attemptResolvedReviews")}</dt><dd>{formatNumber(trainingAttempt.resolved_schema_v2_count)}</dd></div>
                    <div><dt>{t("attemptUsableRows")}</dt><dd>{formatNumber(trainingAttempt.usable_training_rows)}</dd></div>
                    <div><dt>{t("attemptExcludedRows")}</dt><dd>{formatNumber(attemptExcludedCount)}</dd></div>
                  </dl>
                </section>

                <div className="tdl-attempt-detail-grid">
                  <section className="tdl-attempt-block" aria-labelledby="attempt-class-heading">
                    <h4 id="attempt-class-heading">{t("attemptClassHeading")}</h4>
                    <dl className="tdl-attempt-class-counts">
                      {resolvedClasses.map(({ value, labelKey, tone }) => (
                        <div className={tone} key={value}>
                          <dt>{t(labelKey)}</dt>
                          <dd>{formatNumber(trainingAttempt.class_counts_after_text_filter[value])}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>

                  <section className="tdl-attempt-block" aria-labelledby="attempt-split-heading">
                    <h4 id="attempt-split-heading">{t("attemptSplitHeading")}</h4>
                    <p>{t("attemptSplitHelp")}</p>
                    {trainingAttempt.split.computable ? (
                      <dl className="tdl-attempt-split">
                        <div><dt>{t("attemptTrainingRows")}</dt><dd>{formatNumber(trainingAttempt.split.training_rows)}</dd></div>
                        <div><dt>{t("attemptValidationRows")}</dt><dd>{formatNumber(trainingAttempt.split.validation_rows)}</dd></div>
                        <div><dt>{t("attemptTestRows")}</dt><dd>{formatNumber(trainingAttempt.split.test_rows)}</dd></div>
                      </dl>
                    ) : <p className="tdl-attempt-split-warning">{t("attemptSplitUnavailable")}</p>}
                  </section>
                </div>

                {attemptReadiness ? (
                  <section className="tdl-attempt-block tdl-attempt-gates" aria-labelledby="attempt-gates-heading">
                    <div>
                      <h4 id="attempt-gates-heading">{t("attemptGateHeading")}</h4>
                      <p>{t(attemptIsSmokeTest ? "attemptSmokeChecks" : "attemptProductionChecks")}</p>
                    </div>
                    <ul>
                      {attemptReadiness.gates.map((gate) => (
                        <li className={gate.passed ? "passed" : "failed"} key={gate.name}>
                          <i aria-hidden="true" />
                          <div>
                            <strong>{t(trainingGateLabelKeys[gate.name])}</strong>
                            <span>{t("attemptGateValue", {
                              actual: formatAttemptGateValue(gate, gate.actual),
                              minimum: formatAttemptGateValue(gate, gate.minimum),
                            })}</span>
                          </div>
                          <b>{t(gate.passed ? "attemptGatePassed" : "attemptGateFailed")}</b>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </article>
            ) : null}
          </section>

          <section className="tdl-section tdl-model-story" aria-labelledby="model-story-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("modelStoryEyebrow")}</p>
                <h2 id="model-story-heading">{t("modelStoryHeading")}</h2>
                <p>{t("modelStoryDescription")}</p>
              </div>
              <strong className={`tdl-model-stage ${trainingAttempt?.training_performed ? "complete" : "collecting"}`}>
                <i aria-hidden="true" />
                {trainingAttempt?.training_performed ? t("modelCreated") : t("modelStatusCollecting")}
              </strong>
            </div>

            <article className="tdl-model-explainer">
              <div>
                <h3>{t("modelPlainHeading")}</h3>
                <p>{t("modelPlainHelp")}</p>
              </div>
              <ol aria-label={t("modelFlowAria")}>
                {[
                  ["modelFlowHuman", "modelFlowHumanHelp"],
                  ["modelFlowText", "modelFlowTextHelp"],
                  ["modelFlowSplit", "modelFlowSplitHelp"],
                  ["modelFlowFit", "modelFlowFitHelp"],
                  ["modelFlowEvaluate", "modelFlowEvaluateHelp"],
                ].map(([heading, help], index) => (
                  <li className={index === 0 && !trainingAttempt?.training_performed ? "current" : ""} key={heading}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{t(heading as MessageKey)}</strong>
                    <small>{t(help as MessageKey)}</small>
                  </li>
                ))}
              </ol>
            </article>

            {attemptSnapshotDiffers && trainingAttempt ? (
              <p className="tdl-snapshot-notice" role="status">
                <span aria-hidden="true">i</span>
                {t("snapshotDifferent", {
                  attempt: formatNumber(trainingAttempt.latest_review_count),
                  current: formatNumber(summary?.total_articles ?? 0),
                })}
              </p>
            ) : null}

            <div className="tdl-visual-grid">
              <article className="tdl-visual-card" aria-labelledby="current-balance-chart-heading">
                <header>
                  <div>
                    <p className="eyebrow">{t("latestReviews")}</p>
                    <h3 id="current-balance-chart-heading">{t("currentBalanceChartHeading")}</h3>
                  </div>
                  <strong>{formatNumber(summary?.training_eligible ?? 0)}</strong>
                </header>
                <p>{t("currentBalanceChartHelp")}</p>
                <ul className="tdl-balance-chart">
                  {resolvedClasses.map(({ value, labelKey, tone }) => (
                    <li className={tone} key={value}>
                      <span>{t(labelKey)}</span>
                      <i aria-hidden="true"><b style={{ width: `${(classCounts[value] / currentClassMaximum) * 100}%` }} /></i>
                      <strong>{formatNumber(classCounts[value])}</strong>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="tdl-visual-card" aria-labelledby="attempt-split-chart-heading">
                <header>
                  <div>
                    <p className="eyebrow">{t("attemptSaved", { time: trainingAttempt ? formatEastern(trainingAttempt.created_at) : "—" })}</p>
                    <h3 id="attempt-split-chart-heading">{t("savedSplitChartHeading")}</h3>
                  </div>
                </header>
                <p>{t("savedSplitChartHelp")}</p>
                {trainingAttempt?.split.computable ? (
                  <>
                    <div className="tdl-split-chart">
                      {resolvedClasses.map(({ value, labelKey, tone }) => (
                        <div className={`tdl-split-chart-row ${tone}`} key={value}>
                          <strong>{t(labelKey)}</strong>
                          {splitPeriods.map((period) => {
                            const count = trainingAttempt.split.class_counts[period.value][value];
                            return (
                              <div key={period.value}>
                                <small>{period.label}</small>
                                <i aria-hidden="true"><b style={{ width: `${(count / splitClassMaximum) * 100}%` }} /></i>
                                <span>{formatNumber(count)}</span>
                              </div>
                            );
                          })}
                        </div>
                      ))}
                    </div>
                    <p className={`tdl-split-gap ${splitGapLabels.length ? "warning" : "complete"}`}>
                      {splitGapLabels.length
                        ? t("splitGap", { classes: splitGapLabels.join(", ") })
                        : t("noSplitGap")}
                    </p>
                  </>
                ) : (
                  <p className="tdl-chart-empty">{trainingAttempt ? t("savedSplitUnavailable") : t("savedAttemptUnavailable")}</p>
                )}
              </article>
            </div>

            <article className="tdl-map-card" aria-labelledby="training-map-heading">
              <header>
                <div>
                  <p className="eyebrow">{t("modelStoryEyebrow")}</p>
                  <h3 id="training-map-heading">{t("mapHeading")}</h3>
                  <p>{t("mapHelp")}</p>
                </div>
                {mapGeography ? (
                  <dl>
                    <div><dt>{t("mapMapped", { plotted: formatNumber(returnedMappedRows), mapped: formatNumber(mapGeography.mappable_rows) })}</dt><dd>{formatNumber(returnedMappedRows)}</dd></div>
                    <div><dt>{t("mapExcluded", { count: formatNumber(mapGeography.unmappable_rows) })}</dt><dd>{formatNumber(mapGeography.unmappable_rows)}</dd></div>
                  </dl>
                ) : null}
              </header>

              {mapLocations.length ? (
                <>
                  <div className="tdl-map-layout">
                    <div>
                      <div className="tdl-world-map">
                        <svg aria-hidden="true" preserveAspectRatio="xMidYMid meet" viewBox="0 0 960 480">
                          <g className="tdl-map-graticule">
                            {[-120, -60, 0, 60, 120].map((longitude) => {
                              const { x } = projectMapPosition(longitude, 0);
                              return <line key={`longitude-${longitude}`} x1={x} x2={x} y1="0" y2="480" />;
                            })}
                            {[-60, -30, 0, 30, 60].map((latitude) => {
                              const { y } = projectMapPosition(0, latitude);
                              return <line key={`latitude-${latitude}`} x1="0" x2="960" y1={y} y2={y} />;
                            })}
                          </g>
                          <g className="tdl-map-countries">
                            {worldPaths.map((path, index) => <path d={path} key={index} />)}
                          </g>
                        </svg>
                        <div className="tdl-map-pins">
                          {mapLocations.map((location) => {
                            const { x, y } = projectMapPosition(location.longitude, location.latitude);
                            const dominantDecision = dominantLocationDecision(location);
                            const tone = labelTone(dominantDecision);
                            const category = dominantDecision === "mixed"
                              ? t("mapMixed")
                              : t(resolvedClasses.find(({ value }) => value === dominantDecision)?.labelKey ?? "mapMixed");
                            const selected = selectedMapLocation === location;
                            return (
                              <button
                                aria-label={t("mapLocationAria", { location: location.location_name, count: formatNumber(location.article_count), category })}
                                aria-pressed={selected}
                                className={`${tone} ${selected ? "selected" : ""}`}
                                key={`${location.location_name}-${location.latitude}-${location.longitude}`}
                                onClick={() => setSelectedMapLocation(location)}
                                style={{ left: `${(x / 960) * 100}%`, top: `${(y / 480) * 100}%` }}
                                title={`${location.location_name} — ${formatNumber(location.article_count)} — ${category}`}
                                type="button"
                              ><span>{formatNumber(location.article_count)}</span></button>
                            );
                          })}
                        </div>
                        {worldMapState === "loading" ? <p className="tdl-map-state" role="status">{t("mapLoading")}</p> : null}
                        {worldMapState === "error" ? <p className="tdl-map-state warning" role="status">{t("mapBoundaryUnavailable")}</p> : null}
                      </div>
                      <ul className="tdl-map-legend" aria-label={t("mapLegendHeading")}>
                        {resolvedClasses.map(({ value, labelKey, tone }) => (
                          <li className={tone} key={value}><i aria-hidden="true" />{t(labelKey)}</li>
                        ))}
                        <li className="mixed"><i aria-hidden="true" />{t("mapMixed")}</li>
                      </ul>
                      <p className="tdl-map-note">{t("mapMeaningNote")}</p>
                      {mapGeography?.truncated ? (
                        <p className="tdl-map-note warning">
                          {t("mapTruncated", {
                            returned: formatNumber(mapGeography.locations_returned),
                            total: formatNumber(mapGeography.unique_locations),
                            rows: formatNumber(Math.max(0, mapGeography.mappable_rows - returnedMappedRows)),
                          })}
                        </p>
                      ) : null}
                      <a className="tdl-map-source" href="https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/" rel="noreferrer" target="_blank">{t("naturalEarthAttribution")} ↗</a>
                    </div>

                    <aside className="tdl-map-locations" aria-labelledby="mapped-location-list-heading">
                      <div>
                        <h4 id="mapped-location-list-heading">{t("mapListHeading")}</h4>
                        <span>{t("mapListShowing", { shown: formatNumber(listedMapLocations.length), total: formatNumber(mapGeography?.unique_locations ?? mapLocations.length) })}</span>
                      </div>
                      {selectedMapLocation ? (
                        <section className="tdl-map-selection" aria-live="polite">
                          <small>{t("mapSelected")}</small>
                          <strong>{selectedMapLocation.location_name}</strong>
                          <span>{t("mapLocationCount", { count: formatNumber(selectedMapLocation.article_count) })}</span>
                          <ul>
                            {resolvedClasses
                              .filter(({ value }) => selectedMapLocation.class_counts[value] > 0)
                              .map(({ value, labelKey, tone }) => (
                                <li className={tone} key={value}><i aria-hidden="true" />{t(labelKey)} <b>{formatNumber(selectedMapLocation.class_counts[value])}</b></li>
                              ))}
                          </ul>
                        </section>
                      ) : null}
                      <ol>
                        {listedMapLocations.map((location) => (
                          <li key={`${location.location_name}-${location.latitude}-${location.longitude}`}>
                            <button onClick={() => setSelectedMapLocation(location)} type="button">
                              <span>{location.location_name}</span>
                              <small>{location.country_code || `${location.latitude.toFixed(1)}, ${location.longitude.toFixed(1)}`}</small>
                              <strong>{formatNumber(location.article_count)}</strong>
                            </button>
                          </li>
                        ))}
                      </ol>
                    </aside>
                  </div>
                </>
              ) : (
                <p className="tdl-map-empty">{t("mapUnavailable")}</p>
              )}
            </article>
          </section>

          <section className="tdl-section" aria-labelledby="readiness-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("readinessOverview")}</p>
                <h2 id="readiness-heading">{t("readinessHeading")}</h2>
                <p>{t("readinessDescription")}</p>
              </div>
              <a className="tdl-export-link" download="crisispulse-training-articles.csv" href={trainingCSVURL}>{t("exportCsv")}</a>
            </div>

            <div className="tdl-summary-grid">
              <article>
                <span>{t("eligibleLabels")}</span>
                <strong>{formatNumber(summary?.training_eligible ?? 0)}</strong>
                <p>{t("eligibleDefinition")}</p>
              </article>
              <article>
                <span>{t("excludedLabels")}</span>
                <strong>{formatNumber(summary?.excluded ?? 0)}</strong>
                <p>{t("excludedDefinition")}</p>
              </article>
              <article>
                <span>{t("latestReviews")}</span>
                <strong>{formatNumber(summary?.total_articles ?? 0)}</strong>
                <p>{t("currentDatasetDefinition")}</p>
              </article>
              <article>
                <span>{t("smallestClass")}</span>
                <strong>{formatNumber(smallestClassCount)}</strong>
                <p>{t("smallestClassDefinition")}</p>
              </article>
            </div>

            <div className="tdl-gates">
              <article className="pending">
                <header>
                  <div>
                    <span>01</span>
                    <h3>{t("cpuGate")}</h3>
                  </div>
                  <b>{t("notReady")}</b>
                </header>
                <p>{t("cpuGatePendingHelp")}</p>
                <div className="tdl-gate-measure">
                  <span>{t("labelsTotalProgress", { current: formatNumber(summary?.training_eligible ?? 0), target: formatNumber(CPU_TOTAL_GATE) })}</span>
                  <span
                    aria-label={t("labelsTotalProgress", { current: formatNumber(summary?.training_eligible ?? 0), target: formatNumber(CPU_TOTAL_GATE) })}
                    aria-valuemax={CPU_TOTAL_GATE}
                    aria-valuemin={0}
                    aria-valuenow={Math.min(summary?.training_eligible ?? 0, CPU_TOTAL_GATE)}
                    className="tdl-progress"
                    role="progressbar"
                  ><i style={{ width: `${clampPercent(summary?.training_eligible ?? 0, CPU_TOTAL_GATE)}%` }} /></span>
                </div>
                <div className="tdl-gate-measure">
                  <span>{t("labelsClassProgress", { current: formatNumber(smallestClassCount), target: formatNumber(CPU_CLASS_GATE) })}</span>
                  <span
                    aria-label={t("labelsClassProgress", { current: formatNumber(smallestClassCount), target: formatNumber(CPU_CLASS_GATE) })}
                    aria-valuemax={CPU_CLASS_GATE}
                    aria-valuemin={0}
                    aria-valuenow={Math.min(smallestClassCount, CPU_CLASS_GATE)}
                    className="tdl-progress"
                    role="progressbar"
                  ><i style={{ width: `${clampPercent(smallestClassCount, CPU_CLASS_GATE)}%` }} /></span>
                </div>
                <ul className="tdl-gate-checks">
                  {cpuAudits.map((audit) => (
                    <li className={audit.status} key={audit.label}>
                      <i aria-hidden="true" />
                      <span>{audit.label}</span>
                      <strong>{audit.value}</strong>
                      <small>{gateStatusLabel(audit.status)}</small>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="pending">
                <header>
                  <div>
                    <span>02</span>
                    <h3>{t("gpuGate")}</h3>
                  </div>
                  <b>{t("notReady")}</b>
                </header>
                <p>{t("gpuGatePendingHelp")}</p>
                <div className="tdl-gate-measure">
                  <span>{t("labelsTotalProgress", { current: formatNumber(summary?.training_eligible ?? 0), target: formatNumber(GPU_TOTAL_GATE) })}</span>
                  <span
                    aria-label={t("labelsTotalProgress", { current: formatNumber(summary?.training_eligible ?? 0), target: formatNumber(GPU_TOTAL_GATE) })}
                    aria-valuemax={GPU_TOTAL_GATE}
                    aria-valuemin={0}
                    aria-valuenow={Math.min(summary?.training_eligible ?? 0, GPU_TOTAL_GATE)}
                    className="tdl-progress"
                    role="progressbar"
                  ><i style={{ width: `${clampPercent(summary?.training_eligible ?? 0, GPU_TOTAL_GATE)}%` }} /></span>
                </div>
                <div className="tdl-gate-measure">
                  <span>{t("labelsClassProgress", { current: formatNumber(smallestClassCount), target: formatNumber(GPU_CLASS_GATE) })}</span>
                  <span
                    aria-label={t("labelsClassProgress", { current: formatNumber(smallestClassCount), target: formatNumber(GPU_CLASS_GATE) })}
                    aria-valuemax={GPU_CLASS_GATE}
                    aria-valuemin={0}
                    aria-valuenow={Math.min(smallestClassCount, GPU_CLASS_GATE)}
                    className="tdl-progress"
                    role="progressbar"
                  ><i style={{ width: `${clampPercent(smallestClassCount, GPU_CLASS_GATE)}%` }} /></span>
                </div>
                <ul className="tdl-gate-checks">
                  {gpuAudits.map((audit) => (
                    <li className={audit.status} key={audit.label}>
                      <i aria-hidden="true" />
                      <span>{audit.label}</span>
                      <strong>{audit.value}</strong>
                      <small>{gateStatusLabel(audit.status)}</small>
                    </li>
                  ))}
                </ul>
              </article>
            </div>
            <p className="tdl-quality-caveat"><span aria-hidden="true">i</span>{t("qualityCaveat")}</p>
            <aside className="tdl-boundaries" aria-labelledby="training-boundaries-heading">
              <h3 id="training-boundaries-heading">{t("boundariesHeading")}</h3>
              <ul>
                <li>{t("measurementBoundary")}</li>
                <li>{t("uncertainBoundary")}</li>
                <li>{t("balanceBoundary")}</li>
                <li>{t("scopeBoundary")}</li>
                <li>{t("forecastBoundary")}</li>
                <li>{t("modelInputsBoundary")}</li>
                <li>{t("splitBoundary")}</li>
              </ul>
            </aside>
          </section>

          <section className="tdl-section tdl-balance-section" aria-labelledby="class-balance-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("classBalance")}</p>
                <h2 id="class-balance-heading">{t("classBalanceHeading")}</h2>
                <p>{t("classBalanceDescription")}</p>
              </div>
            </div>
            <div className="tdl-class-grid">
              {resolvedClasses.map((classDefinition) => {
                const count = classCounts[classDefinition.value];
                return (
                  <article className={classDefinition.tone} key={classDefinition.value}>
                    <header>
                      <h3>{t(classDefinition.labelKey)}</h3>
                      <strong>{formatNumber(count)}</strong>
                    </header>
                    <p>{t("classCount", { count: formatNumber(count) })}</p>
                    <div className="tdl-class-measure">
                      <span><b>{t("cpuMinimum")}</b><small>{formatNumber(count)}/{formatNumber(CPU_CLASS_GATE)}</small></span>
                      <span className="tdl-progress" role="progressbar" aria-label={`${t(classDefinition.labelKey)} — ${t("cpuMinimum")}`} aria-valuemin={0} aria-valuemax={CPU_CLASS_GATE} aria-valuenow={Math.min(count, CPU_CLASS_GATE)}><i style={{ width: `${clampPercent(count, CPU_CLASS_GATE)}%` }} /></span>
                    </div>
                    <div className="tdl-class-measure">
                      <span><b>{t("gpuMinimum")}</b><small>{formatNumber(count)}/{formatNumber(GPU_CLASS_GATE)}</small></span>
                      <span className="tdl-progress" role="progressbar" aria-label={`${t(classDefinition.labelKey)} — ${t("gpuMinimum")}`} aria-valuemin={0} aria-valuemax={GPU_CLASS_GATE} aria-valuenow={Math.min(count, GPU_CLASS_GATE)}><i style={{ width: `${clampPercent(count, GPU_CLASS_GATE)}%` }} /></span>
                    </div>
                  </article>
                );
              })}
            </div>
            <aside className="tdl-smart-review-cta" aria-labelledby="smart-review-cta-heading">
              <div>
                <p className="eyebrow">{t("smartReviewEyebrow")}</p>
                <h3 id="smart-review-cta-heading">{t("smartReviewHeading")}</h3>
                <p>{t("smartReviewDescription")}</p>
                <small>{t("smartReviewHint")}</small>
              </div>
              <Link href="/admin#article-quality">{t("openSmartReviewQueue")}<span aria-hidden="true">→</span></Link>
            </aside>
          </section>

          <section className="tdl-section tdl-eligibility" aria-labelledby="eligibility-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("eligibleLabels")}</p>
                <h2 id="eligibility-heading">{t("eligibilityHeading")}</h2>
                <p>{t("eligibilityDescription")}</p>
              </div>
            </div>
            <dl>
              <div className="eligible"><dt>{t("eligibleForTraining")}</dt><dd>{formatNumber(summary?.training_eligible ?? 0)}</dd></div>
              <div className="uncertain"><dt>{t("excludedUncertain")}</dt><dd>{formatNumber(summary?.exclusion_reason_counts.uncertain ?? 0)}</dd></div>
              <div className="legacy"><dt>{t("excludedLegacy")}</dt><dd>{formatNumber(summary?.exclusion_reason_counts.legacy_schema ?? 0)}</dd></div>
              <div><dt>{t("exclusionMismatch")}</dt><dd>{formatNumber(otherExcluded)}</dd></div>
            </dl>
          </section>

          <section className="tdl-section tdl-funnel-section" aria-labelledby="archive-funnel-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("archiveFunnel")}</p>
                <h2 id="archive-funnel-heading">{t("archiveFunnelHeading")}</h2>
                <p>{t("archiveFunnelDescription")}</p>
              </div>
            </div>
            <ol className="tdl-funnel">
              <li>
                <span>01</span>
                <strong>{adminStatus ? formatBytes(adminStatus.refresh.retained_raw_bytes) : "—"}</strong>
                <h3>{t("rawArchive")}</h3>
                <p>{adminStatus
                  ? t("rawArchiveDetail", {
                      bytes: formatBytes(adminStatus.refresh.retained_raw_bytes),
                      files: formatNumber(adminStatus.refresh.retained_raw_files),
                    })
                  : t("liveFunnelUnavailable")}
                </p>
              </li>
              <li>
                <span>02</span>
                <strong>{adminStatus?.refresh.archived_articles === undefined ? "—" : formatNumber(adminStatus.refresh.archived_articles)}</strong>
                <h3>{t("permanentArticles")}</h3>
                <p>{adminStatusChecked && !adminStatus ? t("liveFunnelUnavailable") : t("permanentArticlesHelp")}</p>
              </li>
              <li>
                <span>03</span>
                <strong>{formatNumber(summary?.total_articles ?? 0)}</strong>
                <h3>{t("reviewedLabels")}</h3>
                <p>{t("reviewedLabelsHelp")}</p>
              </li>
              <li>
                <span>04</span>
                <strong>{formatNumber(summary?.training_eligible ?? 0)}</strong>
                <h3>{t("eligibleRows")}</h3>
                <p>{t("eligibleRowsHelp")}</p>
              </li>
            </ol>
          </section>

          <section className="tdl-flow" aria-labelledby="data-flow-heading">
            <div>
              <p className="eyebrow">{t("dataFlow")}</p>
              <h2 id="data-flow-heading">{t("dataFlowHeading")}</h2>
              <p>{t("dataFlowDescription")}</p>
            </div>
            <ol>
              <li><span>01</span><strong>{t("flowReview")}</strong><small>{t("flowReviewHelp")}</small></li>
              <li><span>02</span><strong>{t("flowLatest")}</strong><small>{t("flowLatestHelp")}</small></li>
              <li><span>03</span><strong>{t("flowEligibility")}</strong><small>{t("flowEligibilityHelp")}</small></li>
              <li><span>04</span><strong>{t("flowExperiment")}</strong><small>{t("flowExperimentHelp")}</small></li>
            </ol>
          </section>

          <aside className="tdl-credit-note" aria-labelledby="credit-heading">
            <span aria-hidden="true">$0</span>
            <div>
              <p className="eyebrow">{t("creditHeading")}</p>
              <h2 id="credit-heading">{t("creditLocal")}</h2>
              <p>{t("creditCodex")}</p>
            </div>
          </aside>

          <section className="tdl-section tdl-explorer" aria-labelledby="dataset-explorer-heading">
            <div className="tdl-section-heading">
              <div>
                <p className="eyebrow">{t("datasetExplorer")}</p>
                <h2 id="dataset-explorer-heading">{t("datasetExplorerHeading")}</h2>
                <p>{t("datasetExplorerDescription")}</p>
              </div>
              <a className="tdl-export-link" download="crisispulse-training-articles.csv" href={trainingCSVURL}>{t("exportCsv")}</a>
            </div>

            <form className="tdl-filters" onSubmit={(event) => event.preventDefault()} role="search">
              <label>
                <span>{t("search")}</span>
                <input onChange={(event) => setSearch(event.target.value)} placeholder={t("searchPlaceholder")} type="search" value={search} />
              </label>
              <label>
                <span>{t("labelFilter")}</span>
                <select onChange={(event) => setLabelFilter(event.target.value as LabelFilter)} value={labelFilter}>
                  <option value="all">{t("allLabels")}</option>
                  {resolvedClasses.map(({ value, labelKey }) => <option key={value} value={value}>{t(labelKey)}</option>)}
                  <option value="uncertain">{t("uncertain")}</option>
                  <option value="legacy">{t("legacyLabel")}</option>
                </select>
              </label>
              <label>
                <span>{t("eligibilityFilter")}</span>
                <select onChange={(event) => setEligibilityFilter(event.target.value as EligibilityFilter)} value={eligibilityFilter}>
                  <option value="all">{t("allRows")}</option>
                  <option value="eligible">{t("eligibleOnly")}</option>
                  <option value="excluded">{t("excludedOnly")}</option>
                </select>
              </label>
              <button disabled={!hasFilters} onClick={clearFilters} type="button">{t("clearFilters")}</button>
            </form>

            <div className="tdl-results-meta" aria-live="polite">
              <strong>{t("resultsCount", { visible: formatNumber(visibleArticles.length), total: formatNumber(dataset.articles.length) })}</strong>
              <span>{t("easternTime")}</span>
            </div>

            {!dataset.articles.length ? (
              <div className="tdl-table-empty">
                <span aria-hidden="true">0</span>
                <div><h3>{t("emptyHeading")}</h3><p>{t("emptyHelp")}</p></div>
              </div>
            ) : !visibleArticles.length ? (
              <div className="tdl-table-empty">
                <span aria-hidden="true">0</span>
                <div><h3>{t("filteredEmptyHeading")}</h3><p>{t("filteredEmptyHelp")}</p><button onClick={clearFilters} type="button">{t("clearFilters")}</button></div>
              </div>
            ) : (
              <div className="tdl-table-wrap" role="region" aria-label={t("articleTableCaption")}>
                <table>
                  <caption className="tdl-sr-only">{t("articleTableCaption")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("articleColumn")}</th>
                      <th scope="col">{t("publisherColumn")}</th>
                      <th scope="col">{t("labelColumn")}</th>
                      <th scope="col">{t("tagsColumn")}</th>
                      <th scope="col">{t("reviewedColumn")}</th>
                      <th scope="col">{t("eligibilityColumn")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleArticles.map((article) => {
                      const articleTitle = article.title || t("noTitle");
                      const articleURL = safeArticleURL(article.url);
                      return (
                        <tr key={article.article_id}>
                          <td data-label={t("articleColumn")}>
                            {articleURL ? (
                              <a aria-label={t("openPublisherStory", { title: articleTitle })} href={articleURL} rel="noopener noreferrer" target="_blank">{articleTitle}<span aria-hidden="true">↗</span></a>
                            ) : <strong>{articleTitle}</strong>}
                            <small className="tdl-mono">{article.article_id}</small>
                          </td>
                          <td data-label={t("publisherColumn")}>
                            <strong>{article.source_domain || t("unknownPublisher")}</strong>
                            <small>{article.match_strength} · {article.review_bucket}</small>
                          </td>
                          <td data-label={t("labelColumn")}>
                            <span className={`tdl-label-badge ${labelTone(article.decision)}`}>{decisionLabel(article)}</span>
                          </td>
                          <td data-label={t("tagsColumn")}>
                            {article.tags?.length ? <span className="tdl-tags">{article.tags.map((tag) => <i key={tag}>{tag}</i>)}</span> : <small>{t("noTags")}</small>}
                          </td>
                          <td data-label={t("reviewedColumn")}><time dateTime={article.reviewed_at}>{formatEastern(article.reviewed_at)}</time></td>
                          <td data-label={t("eligibilityColumn")}>
                            <span className={`tdl-eligibility-badge ${article.training_eligible ? "eligible" : "excluded"}`}>{article.training_eligible ? t("eligible") : t("excluded")}</span>
                            <small>{exclusionLabel(article)}</small>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}

      <footer className="tdl-footer">
        <p><strong>{t("safeReadOnly")}</strong> — {t("safeReadOnlyHelp")}</p>
        <Link href="/admin">{t("admin")}</Link>
      </footer>
    </main>
  );
}
