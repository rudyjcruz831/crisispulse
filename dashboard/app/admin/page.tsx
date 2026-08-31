"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import bundledDashboardData from "../../data/dashboard.json";
import { defineMessages, formatMessage, LanguageSwitcher, useLocale } from "../i18n";

const messages = defineMessages({
  documentTitle: "CrisisPulse Admin — Operations console",
  documentDescription: "Private local operations view for CrisisPulse data, forecasts, reviews, and readiness.",
  brandHome: "CrisisPulse dashboard home",
  primaryNavigation: "Primary navigation",
  dashboard: "Dashboard",
  admin: "Admin",
  trainingData: "Training data",
  liveOperations: "Live operations",
  checkingOperations: "Checking operations",
  verifiedSnapshot: "Verified snapshot",
  adminSections: "Admin sections",
  status: "Status",
  operations: "Operations",
  forecasts: "Forecasts",
  quality: "Quality",
  operationsConsole: "Operations console",
  heroTitle: "Know what is working before customers do.",
  heroDescription: "One private view for data freshness, forecasts, model health, human review, and the work remaining before a reliable paid pilot.",
  currentSystemHealth: "Current system health",
  currentStatus: "Current status",
  operatingNormally: "Operating normally",
  operationsStatusUnavailable: "Operations status unavailable",
  attentionNeeded: "Attention needed",
  lastSuccessfulRefresh: "Last successful refresh {time}.",
  latestRetainedData: "Latest retained data {time}.",
  easternTime: "Times are shown in U.S. Eastern Time.",
  checking: "Checking…",
  checkNow: "Check now",
  operationsSummary: "Operations summary",
  refreshHealth: "Refresh health",
  sinceLastSuccess: "Since last success",
  waitingForLiveStatus: "Waiting for live status",
  openForecasts: "Open forecasts",
  futureOutcomesCollecting: "Future outcomes still collecting",
  articleReviews: "Article reviews",
  balancedRatesUnlocked: "Balanced quality rates unlocked",
  reviewBalanceNeeded: "Strong and blocked review balance still needed",
  reviewMinimumRemaining: "{count} until the total minimum; balance also required",
  modelHoldout: "Model holdout",
  oneLaterRow: "1 later row",
  laterRows: "{count} later rows",
  operatingChecks: "Operating checks",
  liveSystemChecklist: "Live system checklist",
  healthy: "Healthy",
  checkStatus: "Check status",
  controlsReadOnly: "The page checks the local API every minute. No operational control here can alter or delete data.",
  localApi: "Local API",
  connected: "Connected",
  snapshotFallback: "Snapshot fallback",
  dataRefresh: "15-minute data refresh",
  statusUnavailable: "Status unavailable",
  refreshRunning: "Refresh in progress",
  refreshCompleted: "Refresh completed",
  refreshNeedsAttention: "Refresh needs attention",
  dashboardSnapshot: "Dashboard snapshot",
  chronologicalModel: "Chronological model",
  benchmarkReady: "Benchmark ready",
  unavailable: "Unavailable",
  articleFilterEvaluation: "Article filter evaluation",
  resolvedOf: "{resolved} of {minimum} resolved",
  nextRefreshExpected: "Next refresh expected",
  filesProcessed: "Files processed last run",
  permanentArchive: "Permanent article archive",
  archiveRunDetails: "{bytes} compressed · {count} new last run",
  preservedBeforeRotation: "Preserved before raw rotation",
  titleBackfillDetails: "{added} titles added last run · {remaining} remaining",
  oneTitleBackfill: "1 title added last run · {remaining} remaining",
  titleBackfillPending: "Gradual title backfill pending",
  rawArchiveUsage: "Raw archive usage",
  filesRetained: "{count} files retained",
  oneFileRetained: "1 file retained",
  storageBudget: "10 GB storage budget",
  reliabilityCheck: "48-hour reliability check",
  checkingReadiness: "Checking readiness",
  goPrivatePilot: "Go: ready for private pilot setup",
  checkRestarted: "Check restarted",
  keepObserving: "Keep observing",
  checkingReliabilityRecord: "Checking the live reliability record.",
  readinessUnavailableHeading: "Live readiness status is unavailable.",
  reliabilityPassed: "The local reliability check passed.",
  reliabilityRestarted: "The 48-hour reliability check restarted.",
  latestCollectionAttention: "The latest collection needs attention.",
  firstRefreshStartsClock: "The first completed refresh starts the clock.",
  backupStillOpen: "Reliability passed; backup verification is still open.",
  keepComputerRunning: "Keep this computer and Docker running.",
  noGoWithoutStatus: "CrisisPulse will not report a Go result until the live admin status is available.",
  readyForPrivateSetup: "Local collection is reliable enough to begin private server and sign-in setup.",
  restartedSummary: "A failed, missed, or stale refresh started a new uninterrupted observation window.",
  evidenceFailClosed: "The reliability record remains fail-closed until a current refresh completes successfully.",
  noElapsedBeforeRefresh: "No elapsed time is counted until a completed scheduled refresh is recorded.",
  backupRequired: "The collection window is complete. A readable safety backup must also be verified.",
  progressWhileRunning: "Progress advances with completed scheduled refreshes; time while the PC is off does not count.",
  waiting: "Waiting",
  stale: "Stale",
  current: "Current",
  outOfDate: "Out of date",
  verified: "Verified",
  failed: "Failed",
  notChecked: "Not checked",
  observed: "{duration} observed",
  remaining: "{duration} remaining",
  reliabilityProgress: "48-hour reliability check progress",
  windowComplete: "{percent}% of the uninterrupted window complete",
  progressUnavailable: "Progress unavailable",
  refreshSuccessRate: "Refresh success rate",
  intervalsCovered: "{covered} of {expected} 15-minute intervals covered",
  oneIntervalCovered: "{covered} of 1 15-minute interval covered",
  waitingFirstRefresh: "Waiting for the first completed refresh",
  recordedProblems: "Recorded problems",
  problemTotals: "{failed} failed · {missed} missed · {interrupted} interrupted since tracking began",
  failureTotalsUnavailable: "Failure totals unavailable",
  currentFreshness: "Current freshness",
  lastCompleted: "Last completed {time}",
  noCompletedRefresh: "No completed refresh recorded",
  safetyBackup: "Safety backup",
  backupVerifiedAt: "Verified {time}",
  backupAge: " · {hours}h old",
  backupCheckFailed: "The latest backup check did not pass",
  backupNotConfirmed: "A readable backup has not been confirmed",
  openReadinessChecks: "Readiness checks still open",
  readinessScope: "Passing this check means CrisisPulse can move to private server and sign-in setup. It does not publish the site or grant public access.",
  blockerSoakNotStarted: "The first completed refresh still needs to start the 48-hour check.",
  blockerSoakInProgress: "The uninterrupted 48-hour reliability check is still running.",
  blockerSoakFailed: "The reliability check restarted after a refresh problem.",
  blockerEvidenceMismatch: "The reliability record does not match the latest completed refresh.",
  blockerRefreshStale: "The latest scheduled refresh is more than 30 minutes old.",
  blockerRefreshUnhealthy: "The latest collection has not completed successfully.",
  blockerCoverage: "Too many scheduled refreshes were missed during this check.",
  blockerBackupNotVerified: "A readable safety backup still needs to be verified.",
  blockerBackupFailed: "The latest safety-backup check did not pass.",
  blockerBackupOld: "The last verified safety backup is more than 26 hours old.",
  blockerReliability: "Local collection reliability has not passed yet.",
  blockerFallback: "One readiness check still needs attention.",
  forecastOperations: "Forecast operations",
  forecastHeading: "Open clocks and model benchmark",
  readOnly: "Read-only",
  region: "Region",
  detected: "Detected",
  outcomeCloses: "Outcome closes",
  remainingColumn: "Remaining",
  modelScore: "Model score",
  storiesDomains: "{stories} {storyUnit} · {domains} {domainUnit}",
  story: "story",
  stories: "stories",
  domain: "domain",
  domains: "domains",
  noPendingForecasts: "No forecast outcomes are currently pending.",
  laterHoldout: "Later holdout",
  averagePrecision: "Average precision",
  alertPrecision: "Alert precision",
  outcomeRecall: "Outcome recall",
  falseAlertsDay: "False alerts/day",
  testPositives: "Test positives",
  benchmarkCaveat: "Exploratory media-spread benchmark—not disaster probability or production validation.",
  filterValidation: "Article filter validation",
  qualityHeading: "Review real examples—even when there are no alerts.",
  qualityDescription: "A balanced daily sample measures strong flood matches separately from stories the safety filters blocked.",
  downloadReviews: "Download reviews (.csv)",
  measurementProgress: "Measurement progress",
  measurementsReady: "First filter measurements are ready.",
  ratesLocked: "Rates stay locked until the sample is credible.",
  resolvedLabel: "resolved article label",
  resolvedLabels: "resolved article labels",
  resolvedProgress: "Resolved article-review progress",
  balancedMinimum: "Balanced strong and blocked minimum reached.",
  totalMinimumBalance: "Total minimum reached; strong and blocked labels still need balance.",
  decisionsRemaining: "{count} more resolved version-2 decisions needed, balanced across strong and blocked matches.",
  oneDecisionRemaining: "1 more resolved version-2 decision needed, balanced across strong and blocked matches.",
  strongMatchRelevance: "Flood-related among strong matches",
  strongResolved: "{count} strong matches resolved",
  oneStrongResolved: "1 strong match resolved",
  blockedRelevance: "Flood-related among blocked",
  blockedResolved: "{count} blocked matches resolved",
  oneBlockedResolved: "1 blocked match resolved",
  qualityCaveat: "Because this sample is deliberately balanced, these are separate filter checks—not an overall accuracy claim.",
  reviewGuide: "Independent article-review protocol",
  openPublisher: "Open the publisher story",
  openPublisherHelp: "Judge the publisher's main story—not navigation, ads, comments, or related-story headlines.",
  judgeFlooding: "Classify the central story",
  judgeFloodingHelp: "A passing flood or climate reference does not define the article. Use the event that the headline and story mainly describe.",
  honestUncertainty: "Apply the precedence rule",
  honestUncertaintyHelp: "Flood observed takes precedence over warning or risk; warning or risk takes precedence over heavy rain. Use Cannot verify only when the evidence cannot support a class.",
  trainingLabelBreakdown: "Training-label breakdown",
  trainingLabelHelp: "These five counts show exactly what the current version-2 reviews can teach a future model.",
  trainingCountsUnavailable: "Training-label counts are temporarily unavailable. Refresh the live status before interpreting these totals.",
  labelPrecedence: "Classify the publisher's central story. Flood observed takes precedence over warning or risk; warning or risk takes precedence over heavy rain. Do not infer flooding from rain, a hurricane, or severe weather alone.",
  floodingReported: "Flood observed",
  floodingReportedDefinition: "The main story confirms floodwater, flood impacts, or recovery from an actual flood.",
  floodRiskWarning: "Flood warning/risk only",
  floodRiskWarningDefinition: "The main story gives an explicit flood watch, warning, forecast, or credible risk, with no flooding confirmed.",
  heavyRainOnly: "Heavy rain only",
  heavyRainOnlyDefinition: "Heavy rain is central, with no observed flooding and no explicit flood watch, warning, or risk.",
  notFloodRelated: "No current flood/rain event",
  notFloodRelatedDefinition: "The page is analysis, another weather hazard, or an unrelated match—not a current flood or heavy-rain event.",
  cannotDetermine: "Cannot verify",
  cannotDetermineDefinition: "The publisher evidence cannot be accessed or is too incomplete, conflicting, or ambiguous to classify.",
  reviewStepOne: "Step 1 · Evidence reviewed",
  reviewStepOneHelp: "Choose the strongest publisher evidence you actually used. This is required and is never a model input.",
  fullArticleBasis: "Full article",
  fullArticleBasisHelp: "You read enough of the publisher's article body to identify the central story.",
  publisherSummaryBasis: "Publisher summary or lede",
  publisherSummaryBasisHelp: "You reviewed a publisher-provided summary or opening paragraph.",
  headlineOnlyBasis: "Publisher headline only",
  headlineOnlyBasisHelp: "Only the publisher headline was available; use a resolved class only when it is explicit.",
  unavailableBasis: "Evidence unavailable",
  unavailableBasisHelp: "The page could not provide enough trustworthy evidence; only Cannot verify is available.",
  reviewStepTwo: "Step 2 · Primary class",
  reviewStepTwoHelp: "Choose one class. The four resolved classes teach the model; Cannot verify is retained for audit but excluded from training.",
  resolvedLabelsGroup: "Resolved article classes",
  cannotVerifyPrompt: "Cannot classify this article from trustworthy publisher evidence?",
  reviewStepThree: "Step 3 · Required evidence detail",
  headlineSupportQuestion: "How does the stored headline support this answer?",
  headlineSupportAutomatic: "Headline support is recorded as sufficient because Headline only was selected.",
  headlineSufficient: "Headline is sufficient",
  headlineSufficientHelp: "The stored headline explicitly supports the selected class.",
  bodyRequired: "Article body was required",
  bodyRequiredHelp: "The selected class is correct, but the headline alone does not establish it.",
  conflictsWithBody: "Headline conflicts with body",
  conflictsWithBodyHelp: "The headline suggests a different class than the publisher's article body.",
  noSignalReasonQuestion: "Why is there no current flood or heavy-rain event?",
  floodContextAnalysis: "Flood context or analysis",
  floodContextAnalysisHelp: "Flooding appears only as history, research, climate context, policy, or analysis.",
  otherWeatherNonFlood: "Other weather, not flood/rain",
  otherWeatherNonFloodHelp: "The central event is wind, hail, heat, snow, fire, or another non-flood hazard.",
  unrelatedFalseMatch: "Unrelated or false match",
  unrelatedFalseMatchHelp: "The page is unrelated, uses flood language figuratively, or matched page clutter.",
  uncertaintyReasonQuestion: "Why can this article not be verified?",
  accessBlocked: "Access blocked or paywalled",
  pageUnavailableReason: "Page unavailable",
  wrongOrJunkPage: "Wrong redirect or junk page",
  multiStoryPage: "Multiple-story page",
  languageBarrier: "Language could not be reviewed",
  insufficientOrConflicting: "Evidence insufficient or conflicting",
  optionalEvidenceDetails: "Optional verified details",
  optionalEvidenceDetailsHelp: "Select only facts the publisher explicitly reports. Blank means not recorded, not proven absent.",
  impactsReported: "Impacts reported",
  storyContext: "Story context",
  fatalityFlag: "Fatality",
  injuryFlag: "Injury",
  evacuationDisplacementFlag: "Evacuation or displacement",
  rescueSearchFlag: "Rescue or search",
  propertyCropDamageFlag: "Property or crop damage",
  transportDisruptionFlag: "Transport disruption",
  utilityDisruptionFlag: "Utility disruption",
  aftermathRecoveryFlag: "Aftermath or recovery",
  climateBackgroundFlag: "Climate background",
  historicalBackgroundFlag: "Historical background",
  policyPreparednessFlag: "Policy or preparedness",
  saveReview: "Save review",
  saveCorrection: "Save correction",
  editReview: "Edit review",
  cancelCorrection: "Cancel",
  reviewReadOnly: "Saved review",
  protocolMetadataMissing: "This older version-2 review has no structured protocol details. Its primary label remains valid; edit only if a correction is needed.",
  legacyContextTags: "Legacy tags (read-only)",
  auditContext: "Post-decision audit context",
  auditContextHelp: "These upstream signals were hidden until after the independent human decision.",
  auditThemes: "GDELT themes",
  auditSelection: "Queue selection",
  chooseBasisFirst: "Choose the evidence reviewed before selecting a primary class.",
  completeRequiredReviewFields: "Complete the required evidence details before saving.",
  contextTags: "Optional context tags",
  contextTagsHelp: "Add up to 8 details that describe the story. They help prepare future training data; they do not replace the primary label or control alerts.",
  suggestedContextTags: "Suggested details",
  customContextTag: "Add your own detail",
  customContextTagPlaceholder: "Example: public-safety",
  addContextTag: "Add",
  contextTagLimit: "You can add up to 8 context tags.",
  contextTagFormat: "Custom tags use lowercase words joined by hyphens, up to 32 characters each.",
  contextTagSaveHelp: "Tags are saved only when you choose a primary label. To update tags on a reviewed article, select its highlighted primary label again to save a correction.",
  removeContextTag: "Remove {tag}",
  fatalityTag: "Fatality",
  fatalityTagHelp: "A death is reported.",
  heavyRainTag: "Heavy rain",
  heavyRainTagHelp: "Intense rainfall is part of the story.",
  floodDamageTag: "Flood damage",
  floodDamageTagHelp: "Floodwater damaged homes, property, or land.",
  evacuationTag: "Evacuation",
  evacuationTagHelp: "People were told or forced to leave.",
  rescueTag: "Rescue",
  rescueTagHelp: "Emergency crews rescued or searched for people.",
  cleanupTag: "Cleanup",
  cleanupTagHelp: "Recovery or cleanup work is described.",
  infrastructureTag: "Infrastructure",
  infrastructureTagHelp: "Roads, utilities, bridges, or public systems were affected.",
  stormImpactTag: "Storm impact",
  stormImpactTagHelp: "The article describes broader effects of a storm.",
  legacyLabel: "Legacy label — re-label required",
  oneLegacyExcluded: "1 older label is excluded from these training counts. If it appears in today’s sample, it will require a detailed label.",
  legacyExcluded: "{count} older labels are excluded from these training counts. Any that appear in today’s sample will require a detailed label.",
  answerSaved: "Answer saved",
  notSaved: "Not saved",
  needsReview: "Needs review",
  savingAnswer: "Saving answer",
  saving: "Saving…",
  noQueueRemaining: "No articles in today’s queue remain.",
  oneQueueRemaining: "1 article still needs review.",
  manyQueueRemaining: "{count} articles still need review.",
  savedUncertain: "Saved as {decision}. It moved to Reviewed, but Cannot verify does not count toward the 20 resolved labels. {remaining}",
  savedResolved: "Saved as {decision}. The card was removed from Needs review. {remaining}",
  sampleChanged: "This daily sample changed before the answer was saved. The list is refreshing; please choose again.",
  saveFailed: "This answer was not saved. Please try again; if it continues, select Check now to confirm the local service is connected.",
  oneNeedsReview: "article needs review",
  manyNeedReview: "articles need review",
  hideReviewed: "Hide reviewed",
  showReviewed: "Show reviewed ({count})",
  strongMatch: "Strong match",
  headlineConflict: "Headline conflict",
  ambiguousMatch: "Ambiguous match",
  manualTitle: "Manually verified publisher title",
  publisherTitle: "Publisher-provided title",
  urlTitle: "Cleaned from publisher URL",
  unavailableTitle: "No trustworthy title available",
  unrecordedTitle: "Title source not recorded",
  highMatchReason: "Explicit flood theme; allowed to contribute to alerts",
  conflictReason: "Headline conflicts with the flood tag; blocked from alerts",
  ambiguousReason: "Ambiguous flood tag; retained for audit but blocked from alerts",
  publisher: "Publisher",
  unknown: "Unknown",
  location: "Location",
  unassignedLocation: "Not confidently assigned",
  seen: "Seen",
  savingThisAnswer: "Saving this answer…",
  reviewArticle: "Review {title}",
  queueClear: "Today’s review queue has no pending cards.",
  queueClearHelp: "Every sampled article has an answer. Overall measurements unlock only after a balanced sample; use Show reviewed if you need to correct one.",
  samplePending: "The first archive-backed daily sample will appear after the next refresh.",
  safeByDesign: "Safe by design.",
  safetyDescription: "Review decisions are append-only. This page cannot delete data, restart services, change billing, or issue an emergency warning.",
  sampleDetails: "Sampled: {sampled} {articleUnit} from {archived} permanently archived {recordUnit} on {date}.",
  smartQueueEyebrow: "Smart review order",
  smartQueueHeading: "Why these articles are first",
  smartQueueDescription: "Unfinished cards stay stable; completed cards leave and fresh gap-targeted cards can fill their places. The pending queue is ordered around the current CPU smoke-test gaps in label balance, time, publishers, inference-ready text, and chronological splits.",
  smartQueueHint: "The queue explains why an article was selected, but never reveals or suggests an answer. Review the publisher evidence independently.",
  smartQueueUnavailable: "Readiness details are unavailable, so the queue is using its deterministic balanced order.",
  smartQueueReviewedRows: "Usable reviewed rows",
  smartQueueArticleDates: "Article dates",
  smartQueuePublishers: "Publisher groups",
  smartQueueInferenceText: "Inference-ready text",
  samplingHint: "Coverage priority",
  samplingWindow: "{window} window",
  trainingWindow: "Training",
  validationWindow: "Validation",
  testWindow: "Final test",
  samplingRank: "Priority {rank}",
  reasonUnderrepresentedClass: "Class gap",
  reasonUnderrepresentedSplit: "Split gap",
  reasonNewArticleDate: "New date",
  reasonNewPublisherGroup: "New publisher",
  reasonInferenceTextAvailable: "Inference text ready",
  reasonNeedsDetailedRelabel: "Detailed re-label",
  reasonBalancedFallback: "Balanced fallback",
  article: "article",
  articles: "articles",
  record: "record",
  records: "records",
  waitingLiveSample: "Waiting for a live sample.",
}, {
  documentTitle: "Administración de CrisisPulse — Consola de operaciones",
  documentDescription: "Vista local privada de datos, pronósticos, revisiones y preparación de CrisisPulse.",
  brandHome: "Inicio del panel de CrisisPulse",
  primaryNavigation: "Navegación principal",
  dashboard: "Panel",
  admin: "Administración",
  trainingData: "Datos de entrenamiento",
  liveOperations: "Operaciones en vivo",
  checkingOperations: "Comprobando operaciones",
  verifiedSnapshot: "Instantánea verificada",
  adminSections: "Secciones de administración",
  status: "Estado",
  operations: "Operaciones",
  forecasts: "Pronósticos",
  quality: "Calidad",
  operationsConsole: "Consola de operaciones",
  heroTitle: "Sepa qué funciona antes que sus clientes.",
  heroDescription: "Una vista privada de la actualidad de los datos, los pronósticos, la salud del modelo, la revisión humana y el trabajo pendiente antes de un piloto pagado confiable.",
  currentSystemHealth: "Estado actual del sistema",
  currentStatus: "Estado actual",
  operatingNormally: "Funcionando con normalidad",
  operationsStatusUnavailable: "Estado de operaciones no disponible",
  attentionNeeded: "Requiere atención",
  lastSuccessfulRefresh: "Última actualización correcta: {time}.",
  latestRetainedData: "Datos conservados más recientes: {time}.",
  easternTime: "Las horas se muestran en la hora del este de EE. UU.",
  checking: "Comprobando…",
  checkNow: "Comprobar ahora",
  operationsSummary: "Resumen de operaciones",
  refreshHealth: "Estado de actualización",
  sinceLastSuccess: "Desde la última correcta",
  waitingForLiveStatus: "Esperando el estado en vivo",
  openForecasts: "Pronósticos abiertos",
  futureOutcomesCollecting: "Resultados futuros aún recopilándose",
  articleReviews: "Revisiones de artículos",
  balancedRatesUnlocked: "Tasas de calidad equilibradas disponibles",
  reviewBalanceNeeded: "Aún se necesita equilibrar revisiones fuertes y bloqueadas",
  reviewMinimumRemaining: "Faltan {count} para el mínimo total; también se requiere equilibrio",
  modelHoldout: "Reserva del modelo",
  oneLaterRow: "1 fila posterior",
  laterRows: "{count} filas posteriores",
  operatingChecks: "Comprobaciones operativas",
  liveSystemChecklist: "Lista de comprobación del sistema en vivo",
  healthy: "Correcto",
  checkStatus: "Comprobar estado",
  controlsReadOnly: "La página comprueba la API local cada minuto. Ningún control operativo puede modificar ni eliminar datos.",
  localApi: "API local",
  connected: "Conectada",
  snapshotFallback: "Instantánea de respaldo",
  dataRefresh: "Actualización de datos cada 15 minutos",
  statusUnavailable: "Estado no disponible",
  refreshRunning: "Actualización en curso",
  refreshCompleted: "Actualización completada",
  refreshNeedsAttention: "La actualización requiere atención",
  dashboardSnapshot: "Instantánea del panel",
  chronologicalModel: "Modelo cronológico",
  benchmarkReady: "Referencia lista",
  unavailable: "No disponible",
  articleFilterEvaluation: "Evaluación del filtro de artículos",
  resolvedOf: "{resolved} de {minimum} resueltas",
  nextRefreshExpected: "Próxima actualización prevista",
  filesProcessed: "Archivos procesados en la última ejecución",
  permanentArchive: "Archivo permanente de artículos",
  archiveRunDetails: "{bytes} comprimidos · {count} nuevos en la última ejecución",
  preservedBeforeRotation: "Conservado antes de rotar los datos sin procesar",
  titleBackfillDetails: "{added} títulos añadidos en la última ejecución · {remaining} pendientes",
  oneTitleBackfill: "1 título añadido en la última ejecución · {remaining} pendientes",
  titleBackfillPending: "Relleno gradual de títulos pendiente",
  rawArchiveUsage: "Uso del archivo sin procesar",
  filesRetained: "{count} archivos conservados",
  oneFileRetained: "1 archivo conservado",
  storageBudget: "Presupuesto de almacenamiento de 10 GB",
  reliabilityCheck: "Comprobación de confiabilidad de 48 horas",
  checkingReadiness: "Comprobando preparación",
  goPrivatePilot: "Adelante: listo para configurar el piloto privado",
  checkRestarted: "Comprobación reiniciada",
  keepObserving: "Seguir observando",
  checkingReliabilityRecord: "Comprobando el registro de confiabilidad en vivo.",
  readinessUnavailableHeading: "El estado de preparación en vivo no está disponible.",
  reliabilityPassed: "La comprobación de confiabilidad local fue superada.",
  reliabilityRestarted: "La comprobación de confiabilidad de 48 horas se reinició.",
  latestCollectionAttention: "La recopilación más reciente requiere atención.",
  firstRefreshStartsClock: "La primera actualización completada inicia el reloj.",
  backupStillOpen: "La confiabilidad fue aprobada; falta verificar la copia de seguridad.",
  keepComputerRunning: "Mantenga esta computadora y Docker en funcionamiento.",
  noGoWithoutStatus: "CrisisPulse no mostrará un resultado de aprobación hasta que esté disponible el estado de administración en vivo.",
  readyForPrivateSetup: "La recopilación local es suficientemente confiable para comenzar a configurar el servidor privado y el inicio de sesión.",
  restartedSummary: "Una actualización fallida, omitida o desactualizada inició una nueva ventana de observación ininterrumpida.",
  evidenceFailClosed: "El registro de confiabilidad permanece bloqueado hasta que una actualización actual termine correctamente.",
  noElapsedBeforeRefresh: "No se cuenta tiempo hasta registrar una actualización programada completada.",
  backupRequired: "La ventana de recopilación terminó. También debe verificarse una copia de seguridad legible.",
  progressWhileRunning: "El progreso avanza con las actualizaciones programadas completadas; el tiempo con la PC apagada no cuenta.",
  waiting: "Esperando",
  stale: "Desactualizado",
  current: "Actual",
  outOfDate: "Vencida",
  verified: "Verificada",
  failed: "Fallida",
  notChecked: "Sin comprobar",
  observed: "{duration} observados",
  remaining: "{duration} restantes",
  reliabilityProgress: "Progreso de la comprobación de confiabilidad de 48 horas",
  windowComplete: "{percent}% de la ventana ininterrumpida completada",
  progressUnavailable: "Progreso no disponible",
  refreshSuccessRate: "Tasa de actualizaciones correctas",
  intervalsCovered: "{covered} de {expected} intervalos de 15 minutos cubiertos",
  oneIntervalCovered: "{covered} de 1 intervalo de 15 minutos cubierto",
  waitingFirstRefresh: "Esperando la primera actualización completada",
  recordedProblems: "Problemas registrados",
  problemTotals: "{failed} fallidas · {missed} omitidas · {interrupted} interrumpidas desde el inicio del seguimiento",
  failureTotalsUnavailable: "Totales de fallos no disponibles",
  currentFreshness: "Actualidad de los datos",
  lastCompleted: "Última completada: {time}",
  noCompletedRefresh: "No se registró ninguna actualización completada",
  safetyBackup: "Copia de seguridad",
  backupVerifiedAt: "Verificada: {time}",
  backupAge: " · hace {hours} h",
  backupCheckFailed: "La última comprobación de la copia de seguridad falló",
  backupNotConfirmed: "No se confirmó una copia de seguridad legible",
  openReadinessChecks: "Comprobaciones de preparación pendientes",
  readinessScope: "Superar esta comprobación permite que CrisisPulse avance a la configuración del servidor privado y el inicio de sesión. No publica el sitio ni concede acceso público.",
  blockerSoakNotStarted: "La primera actualización completada aún debe iniciar la comprobación de 48 horas.",
  blockerSoakInProgress: "La comprobación ininterrumpida de confiabilidad de 48 horas sigue en curso.",
  blockerSoakFailed: "La comprobación de confiabilidad se reinició después de un problema de actualización.",
  blockerEvidenceMismatch: "El registro de confiabilidad no coincide con la última actualización completada.",
  blockerRefreshStale: "La última actualización programada tiene más de 30 minutos.",
  blockerRefreshUnhealthy: "La recopilación más reciente no terminó correctamente.",
  blockerCoverage: "Se omitieron demasiadas actualizaciones programadas durante esta comprobación.",
  blockerBackupNotVerified: "Aún debe verificarse una copia de seguridad legible.",
  blockerBackupFailed: "La última comprobación de la copia de seguridad falló.",
  blockerBackupOld: "La última copia de seguridad verificada tiene más de 26 horas.",
  blockerReliability: "La confiabilidad de la recopilación local aún no fue aprobada.",
  blockerFallback: "Una comprobación de preparación aún requiere atención.",
  forecastOperations: "Operaciones de pronóstico",
  forecastHeading: "Relojes abiertos y referencia del modelo",
  readOnly: "Solo lectura",
  region: "Región",
  detected: "Detectado",
  outcomeCloses: "Cierre del resultado",
  remainingColumn: "Restante",
  modelScore: "Puntuación del modelo",
  storiesDomains: "{stories} {storyUnit} · {domains} {domainUnit}",
  story: "historia",
  stories: "historias",
  domain: "dominio",
  domains: "dominios",
  noPendingForecasts: "Actualmente no hay resultados de pronóstico pendientes.",
  laterHoldout: "Reserva posterior",
  averagePrecision: "Precisión media",
  alertPrecision: "Precisión de alertas",
  outcomeRecall: "Cobertura de resultados",
  falseAlertsDay: "Alertas falsas/día",
  testPositives: "Positivos de prueba",
  benchmarkCaveat: "Referencia exploratoria de propagación mediática; no representa la probabilidad de desastre ni una validación de producción.",
  filterValidation: "Validación del filtro de artículos",
  qualityHeading: "Revise ejemplos reales, incluso cuando no haya alertas.",
  qualityDescription: "Una muestra diaria equilibrada mide por separado las coincidencias fuertes de inundación y las historias bloqueadas por los filtros de seguridad.",
  downloadReviews: "Descargar revisiones (.csv)",
  measurementProgress: "Progreso de medición",
  measurementsReady: "Las primeras mediciones del filtro están listas.",
  ratesLocked: "Las tasas permanecen bloqueadas hasta que la muestra sea fiable.",
  resolvedLabel: "etiqueta de artículo resuelta",
  resolvedLabels: "etiquetas de artículos resueltas",
  resolvedProgress: "Progreso de revisión de artículos resueltos",
  balancedMinimum: "Se alcanzó el mínimo equilibrado de coincidencias fuertes y bloqueadas.",
  totalMinimumBalance: "Se alcanzó el mínimo total; aún hay que equilibrar las etiquetas fuertes y bloqueadas.",
  decisionsRemaining: "Faltan {count} decisiones resueltas de la versión 2, equilibradas entre coincidencias fuertes y bloqueadas.",
  oneDecisionRemaining: "Falta 1 decisión resuelta de la versión 2, equilibrada entre coincidencias fuertes y bloqueadas.",
  strongMatchRelevance: "Relacionadas con inundaciones entre coincidencias fuertes",
  strongResolved: "{count} coincidencias fuertes resueltas",
  oneStrongResolved: "1 coincidencia fuerte resuelta",
  blockedRelevance: "Relacionadas con inundaciones entre las bloqueadas",
  blockedResolved: "{count} coincidencias bloqueadas resueltas",
  oneBlockedResolved: "1 coincidencia bloqueada resuelta",
  qualityCaveat: "Como esta muestra está equilibrada deliberadamente, estas son comprobaciones separadas del filtro, no una afirmación de exactitud general.",
  reviewGuide: "Protocolo independiente de revisión de artículos",
  openPublisher: "Abrir la historia del editor",
  openPublisherHelp: "Juzgue la historia principal del editor, no la navegación, los anuncios, los comentarios ni los titulares relacionados.",
  judgeFlooding: "Clasificar la historia central",
  judgeFloodingHelp: "Una referencia pasajera a inundaciones o al clima no define el artículo. Use el evento que describen principalmente el titular y la historia.",
  honestUncertainty: "Aplicar la regla de prioridad",
  honestUncertaintyHelp: "Inundación observada tiene prioridad sobre alerta o riesgo; alerta o riesgo tiene prioridad sobre lluvia intensa. Use No se puede verificar solo cuando la evidencia no permita elegir una clase.",
  trainingLabelBreakdown: "Desglose de etiquetas de entrenamiento",
  trainingLabelHelp: "Estos cinco conteos muestran exactamente qué pueden enseñar las revisiones actuales de la versión 2 a un modelo futuro.",
  trainingCountsUnavailable: "Los conteos de etiquetas de entrenamiento no están disponibles temporalmente. Actualice el estado en vivo antes de interpretar estos totales.",
  labelPrecedence: "Clasifique la historia central del editor. Inundación observada tiene prioridad sobre alerta o riesgo; alerta o riesgo tiene prioridad sobre lluvia intensa. No infiera una inundación solo por lluvia, un huracán o tiempo severo.",
  floodingReported: "Inundación observada",
  floodingReportedDefinition: "La historia principal confirma agua de inundación, impactos o recuperación de una inundación real.",
  floodRiskWarning: "Solo alerta o riesgo de inundación",
  floodRiskWarningDefinition: "La historia principal presenta una vigilancia, alerta, pronóstico o riesgo explícito, sin confirmar una inundación.",
  heavyRainOnly: "Solo lluvia intensa",
  heavyRainOnlyDefinition: "La lluvia intensa es central, sin inundación observada ni vigilancia, alerta o riesgo explícito de inundación.",
  notFloodRelated: "Sin evento actual de inundación o lluvia",
  notFloodRelatedDefinition: "La página es análisis, otro peligro meteorológico o una coincidencia ajena; no es un evento actual de inundación o lluvia intensa.",
  cannotDetermine: "No se puede verificar",
  cannotDetermineDefinition: "No se puede acceder a la evidencia del editor o es demasiado incompleta, contradictoria o ambigua para clasificarla.",
  reviewStepOne: "Paso 1 · Evidencia revisada",
  reviewStepOneHelp: "Elija la evidencia más sólida del editor que realmente utilizó. Es obligatoria y nunca es una entrada del modelo.",
  fullArticleBasis: "Artículo completo",
  fullArticleBasisHelp: "Leyó suficiente contenido del artículo del editor para identificar la historia central.",
  publisherSummaryBasis: "Resumen o entrada del editor",
  publisherSummaryBasisHelp: "Revisó un resumen o párrafo inicial proporcionado por el editor.",
  headlineOnlyBasis: "Solo el titular del editor",
  headlineOnlyBasisHelp: "Solo estaba disponible el titular; use una clase resuelta únicamente cuando sea explícito.",
  unavailableBasis: "Evidencia no disponible",
  unavailableBasisHelp: "La página no aportó evidencia confiable suficiente; solo está disponible No se puede verificar.",
  reviewStepTwo: "Paso 2 · Clase principal",
  reviewStepTwoHelp: "Elija una clase. Las cuatro clases resueltas enseñan al modelo; No se puede verificar se conserva para auditoría, pero se excluye del entrenamiento.",
  resolvedLabelsGroup: "Clases de artículo resueltas",
  cannotVerifyPrompt: "¿No puede clasificar este artículo con evidencia confiable del editor?",
  reviewStepThree: "Paso 3 · Detalle de evidencia obligatorio",
  headlineSupportQuestion: "¿Cómo respalda el titular guardado esta respuesta?",
  headlineSupportAutomatic: "El respaldo del titular se registra como suficiente porque se seleccionó Solo el titular.",
  headlineSufficient: "El titular es suficiente",
  headlineSufficientHelp: "El titular guardado respalda explícitamente la clase seleccionada.",
  bodyRequired: "Se necesitó el cuerpo del artículo",
  bodyRequiredHelp: "La clase seleccionada es correcta, pero el titular por sí solo no la establece.",
  conflictsWithBody: "El titular contradice el cuerpo",
  conflictsWithBodyHelp: "El titular sugiere una clase distinta al cuerpo del artículo del editor.",
  noSignalReasonQuestion: "¿Por qué no hay un evento actual de inundación o lluvia intensa?",
  floodContextAnalysis: "Contexto o análisis de inundaciones",
  floodContextAnalysisHelp: "La inundación aparece solo como historia, investigación, contexto climático, política o análisis.",
  otherWeatherNonFlood: "Otro clima, no inundación o lluvia",
  otherWeatherNonFloodHelp: "El evento central es viento, granizo, calor, nieve, incendio u otro peligro no relacionado con inundaciones.",
  unrelatedFalseMatch: "No relacionado o coincidencia falsa",
  unrelatedFalseMatchHelp: "La página no está relacionada, usa lenguaje figurado o coincidió con contenido secundario.",
  uncertaintyReasonQuestion: "¿Por qué no se puede verificar este artículo?",
  accessBlocked: "Acceso bloqueado o de pago",
  pageUnavailableReason: "Página no disponible",
  wrongOrJunkPage: "Redirección incorrecta o página basura",
  multiStoryPage: "Página con varias historias",
  languageBarrier: "No se pudo revisar el idioma",
  insufficientOrConflicting: "Evidencia insuficiente o contradictoria",
  optionalEvidenceDetails: "Detalles verificados opcionales",
  optionalEvidenceDetailsHelp: "Seleccione solo hechos que el editor informa explícitamente. En blanco significa no registrado, no ausencia comprobada.",
  impactsReported: "Impactos reportados",
  storyContext: "Contexto de la historia",
  fatalityFlag: "Fallecimiento",
  injuryFlag: "Lesión",
  evacuationDisplacementFlag: "Evacuación o desplazamiento",
  rescueSearchFlag: "Rescate o búsqueda",
  propertyCropDamageFlag: "Daños a propiedad o cultivos",
  transportDisruptionFlag: "Interrupción del transporte",
  utilityDisruptionFlag: "Interrupción de servicios",
  aftermathRecoveryFlag: "Consecuencias o recuperación",
  climateBackgroundFlag: "Contexto climático",
  historicalBackgroundFlag: "Contexto histórico",
  policyPreparednessFlag: "Política o preparación",
  saveReview: "Guardar revisión",
  saveCorrection: "Guardar corrección",
  editReview: "Editar revisión",
  cancelCorrection: "Cancelar",
  reviewReadOnly: "Revisión guardada",
  protocolMetadataMissing: "Esta revisión anterior de versión 2 no tiene detalles estructurados del protocolo. Su etiqueta principal sigue siendo válida; edítela solo si necesita una corrección.",
  legacyContextTags: "Etiquetas anteriores (solo lectura)",
  auditContext: "Contexto de auditoría posterior a la decisión",
  auditContextHelp: "Estas señales previas permanecieron ocultas hasta después de la decisión humana independiente.",
  auditThemes: "Temas de GDELT",
  auditSelection: "Selección de cola",
  chooseBasisFirst: "Elija la evidencia revisada antes de seleccionar una clase principal.",
  completeRequiredReviewFields: "Complete los detalles de evidencia obligatorios antes de guardar.",
  contextTags: "Etiquetas de contexto opcionales",
  contextTagsHelp: "Añada hasta 8 detalles que describan la historia. Ayudan a preparar futuros datos de entrenamiento; no sustituyen la etiqueta principal ni controlan las alertas.",
  suggestedContextTags: "Detalles sugeridos",
  customContextTag: "Añadir un detalle propio",
  customContextTagPlaceholder: "Ejemplo: seguridad-pública",
  addContextTag: "Añadir",
  contextTagLimit: "Puede añadir hasta 8 etiquetas de contexto.",
  contextTagFormat: "Las etiquetas propias usan palabras en minúsculas unidas por guiones, con un máximo de 32 caracteres cada una.",
  contextTagSaveHelp: "Las etiquetas se guardan solo al elegir una etiqueta principal. Para actualizar las etiquetas de un artículo revisado, seleccione de nuevo su etiqueta principal resaltada para guardar una corrección.",
  removeContextTag: "Quitar {tag}",
  fatalityTag: "Fallecimiento",
  fatalityTagHelp: "Se informa de una muerte.",
  heavyRainTag: "Lluvia intensa",
  heavyRainTagHelp: "La lluvia intensa forma parte de la historia.",
  floodDamageTag: "Daños por inundación",
  floodDamageTagHelp: "El agua dañó viviendas, propiedades o terrenos.",
  evacuationTag: "Evacuación",
  evacuationTagHelp: "Se pidió u obligó a personas a abandonar el lugar.",
  rescueTag: "Rescate",
  rescueTagHelp: "Los equipos de emergencia rescataron o buscaron personas.",
  cleanupTag: "Limpieza",
  cleanupTagHelp: "Se describen trabajos de recuperación o limpieza.",
  infrastructureTag: "Infraestructura",
  infrastructureTagHelp: "Se afectaron carreteras, servicios, puentes o sistemas públicos.",
  stormImpactTag: "Impacto de la tormenta",
  stormImpactTagHelp: "El artículo describe efectos más amplios de una tormenta.",
  legacyLabel: "Etiqueta anterior — requiere volver a etiquetar",
  oneLegacyExcluded: "1 etiqueta anterior está excluida de estos conteos de entrenamiento. Si aparece en la muestra de hoy, requerirá una etiqueta detallada.",
  legacyExcluded: "{count} etiquetas anteriores están excluidas de estos conteos de entrenamiento. Las que aparezcan en la muestra de hoy requerirán una etiqueta detallada.",
  answerSaved: "Respuesta guardada",
  notSaved: "No se guardó",
  needsReview: "Necesita revisión",
  savingAnswer: "Guardando respuesta",
  saving: "Guardando…",
  noQueueRemaining: "No quedan artículos en la cola de hoy.",
  oneQueueRemaining: "1 artículo aún necesita revisión.",
  manyQueueRemaining: "{count} artículos aún necesitan revisión.",
  savedUncertain: "Guardado como {decision}. Pasó a Revisados, pero No se puede verificar no cuenta para las 20 etiquetas resueltas. {remaining}",
  savedResolved: "Guardado como {decision}. La tarjeta se eliminó de Necesita revisión. {remaining}",
  sampleChanged: "La muestra diaria cambió antes de guardar la respuesta. La lista se está actualizando; elija de nuevo.",
  saveFailed: "Esta respuesta no se guardó. Inténtelo de nuevo; si continúa, seleccione Comprobar ahora para confirmar que el servicio local está conectado.",
  oneNeedsReview: "artículo necesita revisión",
  manyNeedReview: "artículos necesitan revisión",
  hideReviewed: "Ocultar revisados",
  showReviewed: "Mostrar revisados ({count})",
  strongMatch: "Coincidencia fuerte",
  headlineConflict: "Conflicto de titular",
  ambiguousMatch: "Coincidencia ambigua",
  manualTitle: "Título del editor verificado manualmente",
  publisherTitle: "Título proporcionado por el editor",
  urlTitle: "Limpiado de la URL del editor",
  unavailableTitle: "No hay un título confiable disponible",
  unrecordedTitle: "Fuente del título no registrada",
  highMatchReason: "Tema explícito de inundación; puede contribuir a las alertas",
  conflictReason: "El titular contradice la etiqueta de inundación; bloqueado para alertas",
  ambiguousReason: "Etiqueta de inundación ambigua; conservada para auditoría, pero bloqueada para alertas",
  publisher: "Editor",
  unknown: "Desconocido",
  location: "Ubicación",
  unassignedLocation: "No asignada con confianza",
  seen: "Visto",
  savingThisAnswer: "Guardando esta respuesta…",
  reviewArticle: "Revisar {title}",
  queueClear: "La cola de revisión de hoy no tiene tarjetas pendientes.",
  queueClearHelp: "Cada artículo de la muestra tiene una respuesta. Las mediciones generales solo se habilitan tras una muestra equilibrada; use Mostrar revisados si necesita corregir una.",
  samplePending: "La primera muestra diaria respaldada por el archivo aparecerá después de la próxima actualización.",
  safeByDesign: "Seguro por diseño.",
  safetyDescription: "Las decisiones de revisión son de solo anexado. Esta página no puede eliminar datos, reiniciar servicios, cambiar la facturación ni emitir una alerta de emergencia.",
  sampleDetails: "Muestra: {sampled} {articleUnit} de {archived} {recordUnit} del archivo permanente el {date}.",
  smartQueueEyebrow: "Orden de revisión inteligente",
  smartQueueHeading: "Por qué estos artículos aparecen primero",
  smartQueueDescription: "Las tarjetas sin terminar permanecen estables; las completadas salen y nuevas tarjetas dirigidas a las brechas pueden ocupar su lugar. La cola pendiente se ordena según las brechas actuales de la prueba breve de CPU: equilibrio de etiquetas, fechas, editores, texto de inferencia y particiones cronológicas.",
  smartQueueHint: "La cola explica por qué se seleccionó un artículo, pero nunca revela ni sugiere una respuesta. Revise la evidencia del editor de forma independiente.",
  smartQueueUnavailable: "Los detalles de preparación no están disponibles, por lo que la cola usa su orden equilibrado y determinista.",
  smartQueueReviewedRows: "Filas revisadas utilizables",
  smartQueueArticleDates: "Fechas de artículos",
  smartQueuePublishers: "Grupos de editores",
  smartQueueInferenceText: "Texto listo para inferencia",
  samplingHint: "Prioridad de cobertura",
  samplingWindow: "Ventana de {window}",
  trainingWindow: "entrenamiento",
  validationWindow: "validación",
  testWindow: "prueba final",
  samplingRank: "Prioridad {rank}",
  reasonUnderrepresentedClass: "Brecha de clase",
  reasonUnderrepresentedSplit: "Brecha de partición",
  reasonNewArticleDate: "Fecha nueva",
  reasonNewPublisherGroup: "Editor nuevo",
  reasonInferenceTextAvailable: "Texto de inferencia listo",
  reasonNeedsDetailedRelabel: "Reetiquetado detallado",
  reasonBalancedFallback: "Respaldo equilibrado",
  article: "artículo",
  articles: "artículos",
  record: "registro",
  records: "registros",
  waitingLiveSample: "Esperando una muestra en vivo.",
});

type DashboardData = typeof bundledDashboardData;
type ArticleDecision = "reported_flooding" | "flood_risk_warning" | "heavy_rain_only" | "not_flood_related" | "uncertain";
type ResolvedArticleDecision = Exclude<ArticleDecision, "uncertain">;
type LegacyArticleDecision = "relevant" | "not_relevant";
type QualityArticleDecision = ArticleDecision | LegacyArticleDecision;
type ReviewBasis = "full_article" | "publisher_summary" | "headline_only" | "unavailable";
type HeadlineSupport = "sufficient" | "body_required" | "conflicts_with_body";
type NoSignalReason = "flood_context_analysis" | "other_weather_non_flood" | "unrelated_false_match";
type UncertaintyReason = "access_blocked" | "page_unavailable" | "wrong_or_junk_page" | "multi_story_page" | "language_barrier" | "insufficient_or_conflicting";
type ImpactFlag = "fatality" | "injury" | "evacuation_displacement" | "rescue_search" | "property_crop_damage" | "transport_disruption" | "utility_disruption";
type ContextFlag = "aftermath_recovery" | "climate_background" | "historical_background" | "policy_preparedness";
type ArticleReviewDraft = {
  reviewBasis?: ReviewBasis;
  decision?: ArticleDecision;
  headlineSupport?: HeadlineSupport;
  noSignalReason?: NoSignalReason;
  uncertaintyReason?: UncertaintyReason;
  impactFlags: ImpactFlag[];
  contextFlags: ContextFlag[];
};
type QualitySelectionReason =
  | "underrepresented_class"
  | "underrepresented_split"
  | "new_article_date"
  | "new_publisher_group"
  | "inference_text_available"
  | "needs_detailed_relabel"
  | "balanced_fallback";
type QualityArticleSelectionIntent = {
  rank: number;
  sampling_split?: "training" | "validation" | "test";
  reasons: QualitySelectionReason[];
};
type QualityQueueSelectionIntent = {
  strategy: "training_readiness_v1";
  target: "cpu_smoke";
  usable_rows: number;
  usable_rows_minimum: number;
  class_counts: Record<ResolvedArticleDecision, number>;
  class_minimum: number;
  distinct_article_dates: number;
  article_date_minimum: number;
  publisher_groups: number;
  publisher_group_minimum: number;
  inference_text_coverage: number;
  inference_text_minimum: number;
  split_class_counts: Partial<Record<"training" | "validation" | "test", Record<ResolvedArticleDecision, number>>>;
  split_class_minimums: Record<"training" | "validation" | "test", number>;
  readiness_status: "computed" | "unavailable";
  production_minimums?: {
    total_usable_rows: number;
    class_minimum: number;
    article_dates: number;
    publisher_groups: number;
    inference_text_coverage: number;
    split_class_minimums: Record<"training" | "validation" | "test", number>;
  };
};
type QualityArticle = {
  article_id: string;
  seen_at: string;
  title: string;
  title_source?: "manual_override" | "publisher_metadata" | "url_path" | "unavailable";
  url: string;
  source_domain: string;
  location_name: string;
  match_strength: "high" | "weak";
  review_bucket: "high_match" | "headline_conflict" | "ambiguous_match";
  review_reason: string;
  themes: string[];
  quality_flags: string[];
  tags?: string[];
  decision?: QualityArticleDecision;
  decision_schema_version?: number;
  review_protocol_version?: number;
  review_basis?: ReviewBasis;
  headline_support?: HeadlineSupport;
  no_signal_reason?: NoSignalReason;
  uncertainty_reason?: UncertaintyReason;
  impact_flags?: ImpactFlag[];
  context_flags?: ContextFlag[];
  reviewed_at?: string;
  selection_intent?: QualityArticleSelectionIntent;
};
type QualitySample = {
  version: number;
  sample_date: string;
  archive_articles: number;
  eligible_articles: number;
  queue_candidate_articles?: number;
  selection_intent?: QualityQueueSelectionIntent;
  articles: QualityArticle[];
};
type ArticleQualitySummary = {
  total_reviews: number;
  legacy_reviews: number;
  reported_flooding_articles: number;
  flood_risk_warning_articles: number;
  heavy_rain_only_articles: number;
  not_flood_related_articles: number;
  uncertain: number;
  resolved_reviews: number;
  minimum_sample: number;
  remaining_to_sample: number;
  high_resolved: number;
  high_flood_related: number;
  weak_resolved: number;
  weak_flood_related: number;
  high_match_flood_related_rate: number | null;
  weak_match_flood_related_rate: number | null;
  status: "collecting_labels" | "sample_ready";
};
type ArticleReviewResponse = {
  review: {
    article_id: string;
    decision: ArticleDecision;
    decision_schema_version: 2;
    review_protocol_version: 1;
    review_basis: ReviewBasis;
    headline_support?: HeadlineSupport;
    no_signal_reason?: NoSignalReason;
    uncertainty_reason?: UncertaintyReason;
    impact_flags?: ImpactFlag[];
    context_flags?: ContextFlag[];
    reviewed_at: string;
    tags?: string[];
  };
};
type SavingArticleReview = {
  articleID: string;
  decision: ArticleDecision;
};
type QualityNotice = {
  kind: "success" | "error";
  message: string;
};
type SoakStatus = {
  status: "not_started" | "in_progress" | "passed" | "failed";
  started_at: string | null;
  last_observed_at: string | null;
  completed_at: string | null;
  target_hours: number;
  interval_minutes: number;
  observed_minutes: number;
  remaining_minutes: number;
  successful_runs: number;
  expected_runs: number;
  failed_runs: number;
  missed_runs: number;
  interrupted_runs: number;
  current_stale: boolean;
  coverage_percent: number;
  progress_percent: number;
  last_failure_at: string | null;
  last_reset_at: string | null;
  reset_reason: string;
};
type BackupStatus = {
  status: "not_checked" | "verified" | "failed";
  verified_at: string | null;
  age_hours: number | null;
};
type PilotReadiness = {
  status: "not_ready" | "ready_for_pilot_setup";
  local_reliability_passed: boolean;
  backup_verified: boolean;
  blockers: string[];
};
type AdminStatus = {
  service: { name: string; status: string };
  refresh: {
    status: string;
    health: "healthy" | "degraded";
    started_at: string;
    finished_at: string;
    last_success_at: string;
    expected_next_refresh_at: string;
    age_minutes: number;
    message: string;
    processed_files: number;
    downloaded_files: number;
    already_present_files: number;
    retained_raw_files: number;
    retained_raw_bytes?: number;
    raw_storage_limit_bytes?: number;
    pruned_raw_files: number;
    archived_articles?: number;
    new_archived_articles?: number;
    article_archive_bytes?: number;
    title_backfill_attempted_articles?: number;
    title_backfill_updated_articles?: number;
    title_backfill_remaining_articles?: number;
    title_backfill_downgraded_articles?: number;
    soak?: SoakStatus;
  };
  backup?: BackupStatus;
  pilot_readiness?: PilotReadiness;
};

type MessageKey = keyof typeof messages.en;

const formatNumber = (value: number, localeTag: string) => value.toLocaleString(localeTag);
const formatBytes = (value: number | null | undefined, localeTag: string) => {
  if (value === null || value === undefined || value < 0) return "—";
  const compact = (amount: number) => new Intl.NumberFormat(localeTag, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(amount);
  if (value >= 1_000_000_000) return `${compact(value / 1_000_000_000)} GB`;
  if (value >= 1_000_000) return `${compact(value / 1_000_000)} MB`;
  if (value >= 1_000) return `${compact(value / 1_000)} KB`;
  return `${formatNumber(value, localeTag)} B`;
};
const formatEastern = (value: string, localeTag: string) => {
  if (!value) return "—";
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  const date = new Date(hasExplicitTimezone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(localeTag, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
};
const formatPercent = (value: number | null | undefined, localeTag: string) =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat(localeTag, {
      style: "percent",
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
const clampPercent = (value: number | null | undefined) =>
  value === null || value === undefined || !Number.isFinite(value)
    ? 0
    : Math.min(100, Math.max(0, value));
const formatDuration = (value: number | null | undefined, localeTag: string) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const minutes = Math.max(0, Math.round(value));
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours === 0) return `${formatNumber(remainder, localeTag)}m`;
  if (remainder === 0) return `${formatNumber(hours, localeTag)}h`;
  return `${formatNumber(hours, localeTag)}h ${formatNumber(remainder, localeTag)}m`;
};
const formatSampleDate = (value: string, localeTag: string) => {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(localeTag, {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
};
const safeCount = (value: number | null | undefined) =>
  value === null || value === undefined || !Number.isFinite(value)
    ? 0
    : Math.max(0, Math.round(value));
const qualityArticlesURL = "/api/v1/quality/articles";
const qualitySummaryURL = "/api/v1/quality/articles/summary";
const qualityExportURL = "/api/v1/quality/articles/export.csv";
type ArticleReviewOption = {
  value: ArticleDecision;
  labelKey: MessageKey;
  definitionKey: MessageKey;
  countField: "reported_flooding_articles" | "flood_risk_warning_articles" | "heavy_rain_only_articles" | "not_flood_related_articles" | "uncertain";
  tone: string;
  resolved: boolean;
};
const articleReviewOptions: ArticleReviewOption[] = [
  { value: "reported_flooding", labelKey: "floodingReported", definitionKey: "floodingReportedDefinition", countField: "reported_flooding_articles", tone: "reported-flooding", resolved: true },
  { value: "flood_risk_warning", labelKey: "floodRiskWarning", definitionKey: "floodRiskWarningDefinition", countField: "flood_risk_warning_articles", tone: "flood-risk-warning", resolved: true },
  { value: "heavy_rain_only", labelKey: "heavyRainOnly", definitionKey: "heavyRainOnlyDefinition", countField: "heavy_rain_only_articles", tone: "heavy-rain-only", resolved: true },
  { value: "not_flood_related", labelKey: "notFloodRelated", definitionKey: "notFloodRelatedDefinition", countField: "not_flood_related_articles", tone: "not-flood-related", resolved: true },
  { value: "uncertain", labelKey: "cannotDetermine", definitionKey: "cannotDetermineDefinition", countField: "uncertain", tone: "cannot-determine", resolved: false },
];
type ReviewChoiceOption<Value extends string> = {
  value: Value;
  labelKey: MessageKey;
  descriptionKey?: MessageKey;
};
const reviewBasisOptions: ReviewChoiceOption<ReviewBasis>[] = [
  { value: "full_article", labelKey: "fullArticleBasis", descriptionKey: "fullArticleBasisHelp" },
  { value: "publisher_summary", labelKey: "publisherSummaryBasis", descriptionKey: "publisherSummaryBasisHelp" },
  { value: "headline_only", labelKey: "headlineOnlyBasis", descriptionKey: "headlineOnlyBasisHelp" },
  { value: "unavailable", labelKey: "unavailableBasis", descriptionKey: "unavailableBasisHelp" },
];
const headlineSupportOptions: ReviewChoiceOption<HeadlineSupport>[] = [
  { value: "sufficient", labelKey: "headlineSufficient", descriptionKey: "headlineSufficientHelp" },
  { value: "body_required", labelKey: "bodyRequired", descriptionKey: "bodyRequiredHelp" },
  { value: "conflicts_with_body", labelKey: "conflictsWithBody", descriptionKey: "conflictsWithBodyHelp" },
];
const noSignalReasonOptions: ReviewChoiceOption<NoSignalReason>[] = [
  { value: "flood_context_analysis", labelKey: "floodContextAnalysis", descriptionKey: "floodContextAnalysisHelp" },
  { value: "other_weather_non_flood", labelKey: "otherWeatherNonFlood", descriptionKey: "otherWeatherNonFloodHelp" },
  { value: "unrelated_false_match", labelKey: "unrelatedFalseMatch", descriptionKey: "unrelatedFalseMatchHelp" },
];
const uncertaintyReasonOptions: ReviewChoiceOption<UncertaintyReason>[] = [
  { value: "access_blocked", labelKey: "accessBlocked" },
  { value: "page_unavailable", labelKey: "pageUnavailableReason" },
  { value: "wrong_or_junk_page", labelKey: "wrongOrJunkPage" },
  { value: "multi_story_page", labelKey: "multiStoryPage" },
  { value: "language_barrier", labelKey: "languageBarrier" },
  { value: "insufficient_or_conflicting", labelKey: "insufficientOrConflicting" },
];
const impactFlagOptions: ReviewChoiceOption<ImpactFlag>[] = [
  { value: "fatality", labelKey: "fatalityFlag" },
  { value: "injury", labelKey: "injuryFlag" },
  { value: "evacuation_displacement", labelKey: "evacuationDisplacementFlag" },
  { value: "rescue_search", labelKey: "rescueSearchFlag" },
  { value: "property_crop_damage", labelKey: "propertyCropDamageFlag" },
  { value: "transport_disruption", labelKey: "transportDisruptionFlag" },
  { value: "utility_disruption", labelKey: "utilityDisruptionFlag" },
];
const contextFlagOptions: ReviewChoiceOption<ContextFlag>[] = [
  { value: "aftermath_recovery", labelKey: "aftermathRecoveryFlag" },
  { value: "climate_background", labelKey: "climateBackgroundFlag" },
  { value: "historical_background", labelKey: "historicalBackgroundFlag" },
  { value: "policy_preparedness", labelKey: "policyPreparednessFlag" },
];
const articleDecisionValues = new Set<ArticleDecision>(articleReviewOptions.map((option) => option.value));
const getArticleReviewOption = (decision: QualityArticleDecision | undefined) => (
  decision && articleDecisionValues.has(decision as ArticleDecision)
    ? articleReviewOptions.find((option) => option.value === decision) ?? null
    : null
);
const getDetailedArticleDecision = (article: QualityArticle) => (
  article.decision_schema_version === 2
    ? getArticleReviewOption(article.decision)?.value
    : undefined
);
const hasDetailedArticleReview = (article: QualityArticle) => Boolean(getDetailedArticleDecision(article));
const hasLegacyArticleReview = (article: QualityArticle) => Boolean(
  article.decision && !hasDetailedArticleReview(article),
);
const hasProtocolArticleReview = (article: QualityArticle) => (
  hasDetailedArticleReview(article) && article.review_protocol_version === 1
);
const buildArticleReviewDraft = (article: QualityArticle): ArticleReviewDraft => ({
  reviewBasis: hasProtocolArticleReview(article) ? article.review_basis : undefined,
  decision: getDetailedArticleDecision(article),
  headlineSupport: hasProtocolArticleReview(article) ? article.headline_support : undefined,
  noSignalReason: hasProtocolArticleReview(article) ? article.no_signal_reason : undefined,
  uncertaintyReason: hasProtocolArticleReview(article) ? article.uncertainty_reason : undefined,
  impactFlags: hasProtocolArticleReview(article) ? [...(article.impact_flags ?? [])] : [],
  contextFlags: hasProtocolArticleReview(article) ? [...(article.context_flags ?? [])] : [],
});
const isResolvedArticleDecision = (decision: ArticleDecision | undefined): decision is ResolvedArticleDecision => (
  Boolean(decision && decision !== "uncertain")
);
const isArticleReviewDraftComplete = (draft: ArticleReviewDraft) => {
  if (!draft.reviewBasis || !draft.decision) return false;
  if (draft.decision === "uncertain") return Boolean(draft.uncertaintyReason);
  if (draft.reviewBasis === "unavailable" || !draft.headlineSupport) return false;
  return draft.decision !== "not_flood_related" || Boolean(draft.noSignalReason);
};
const reviewBucketMetadata: Record<QualityArticle["review_bucket"], { labelKey: MessageKey; reasonKey: MessageKey }> = {
  high_match: { labelKey: "strongMatch", reasonKey: "highMatchReason" },
  headline_conflict: { labelKey: "headlineConflict", reasonKey: "conflictReason" },
  ambiguous_match: { labelKey: "ambiguousMatch", reasonKey: "ambiguousReason" },
};
const qualitySelectionReasonMessageKeys: Record<QualitySelectionReason, MessageKey> = {
  underrepresented_class: "reasonUnderrepresentedClass",
  underrepresented_split: "reasonUnderrepresentedSplit",
  new_article_date: "reasonNewArticleDate",
  new_publisher_group: "reasonNewPublisherGroup",
  inference_text_available: "reasonInferenceTextAvailable",
  needs_detailed_relabel: "reasonNeedsDetailedRelabel",
  balanced_fallback: "reasonBalancedFallback",
};
const samplingSplitMessageKeys: Record<NonNullable<QualityArticleSelectionIntent["sampling_split"]>, MessageKey> = {
  training: "trainingWindow",
  validation: "validationWindow",
  test: "testWindow",
};
const titleSourceMessageKeys: Record<NonNullable<QualityArticle["title_source"]>, MessageKey> = {
  manual_override: "manualTitle",
  publisher_metadata: "publisherTitle",
  url_path: "urlTitle",
  unavailable: "unavailableTitle",
};
const getTitleSourceMessageKey = (source: QualityArticle["title_source"]): MessageKey => (
  source ? titleSourceMessageKeys[source] : "unrecordedTitle"
);
const getArticleDecisionStatus = (
  article: QualityArticle,
  isSaving: boolean,
): { labelKey: MessageKey; tone: string } => {
  if (isSaving) return { labelKey: "savingAnswer", tone: "saving" };
  if (hasLegacyArticleReview(article)) return { labelKey: "legacyLabel", tone: "legacy" };
  const option = getArticleReviewOption(getDetailedArticleDecision(article));
  if (option) return { labelKey: option.labelKey, tone: option.tone };
  return { labelKey: "needsReview", tone: "pending" };
};
const safeArticleURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
};
const fetchJSONWithTimeout = async <T,>(
  url: string,
  parentSignal?: AbortSignal,
  timeoutMilliseconds = 8_000,
): Promise<T | null> => {
  const controller = new AbortController();
  const abortFromParent = () => controller.abort();
  if (parentSignal?.aborted) controller.abort();
  else parentSignal?.addEventListener("abort", abortFromParent, { once: true });
  const timeout = window.setTimeout(() => controller.abort(), timeoutMilliseconds);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) return null;
    return await response.json() as T;
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
};

export default function AdminPage() {
  const { locale, localeTag } = useLocale();
  const pageMessages = messages[locale];
  const t = (key: MessageKey, values: Record<string, string | number> = {}) => (
    formatMessage(pageMessages[key], values)
  );
  const [dashboardData, setDashboardData] = useState<DashboardData>(bundledDashboardData);
  const [qualitySample, setQualitySample] = useState<QualitySample | null>(null);
  const [qualitySummary, setQualitySummary] = useState<ArticleQualitySummary | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [connection, setConnection] = useState<"loading" | "ready" | "offline">("loading");
  const [adminStatusAvailability, setAdminStatusAvailability] = useState<"loading" | "ready" | "offline">("loading");
  const [checking, setChecking] = useState(false);
  const [savingArticleReview, setSavingArticleReview] = useState<SavingArticleReview | null>(null);
  const [qualityNotice, setQualityNotice] = useState<QualityNotice | null>(null);
  const [showReviewedArticles, setShowReviewedArticles] = useState(false);
  const [articleReviewDrafts, setArticleReviewDrafts] = useState<Record<string, ArticleReviewDraft>>({});
  const [editingArticleID, setEditingArticleID] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const reviewRequestInFlight = useRef(false);
  const focusAfterReview = useRef(false);
  const qualityGridRef = useRef<HTMLDivElement>(null);
  const qualityNoticeRef = useRef<HTMLParagraphElement>(null);
  const { snapshot, forecast } = dashboardData;
  const queueSelectionIntent = qualitySample?.selection_intent?.strategy === "training_readiness_v1"
    ? qualitySample.selection_intent
    : null;
  const pendingQualityArticles = (qualitySample?.articles ?? [])
    .filter((article) => !hasDetailedArticleReview(article))
    .slice()
    .sort((left, right) => {
      const leftSelectionRank = left.selection_intent?.rank;
      const rightSelectionRank = right.selection_intent?.rank;
      const leftRank = typeof leftSelectionRank === "number" && Number.isSafeInteger(leftSelectionRank)
        ? leftSelectionRank
        : Number.MAX_SAFE_INTEGER;
      const rightRank = typeof rightSelectionRank === "number" && Number.isSafeInteger(rightSelectionRank)
        ? rightSelectionRank
        : Number.MAX_SAFE_INTEGER;
      return leftRank - rightRank;
    });
  const reviewedQualityArticles = qualitySample?.articles.filter(hasDetailedArticleReview) ?? [];
  const visibleQualityArticles = showReviewedArticles
    ? qualitySample?.articles ?? []
    : pendingQualityArticles;
  const qualityQueueComplete = Boolean(
    qualitySample && qualitySample.version >= 2 && qualitySample.articles.length === 0,
  );

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

  const refreshAdmin = useCallback(async (signal?: AbortSignal) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setChecking(true);
    // Fail closed while checking so a prior Go result can never linger.
    setAdminStatus(null);
    setAdminStatusAvailability("loading");
    try {
      const statusRequest = fetchJSONWithTimeout<AdminStatus>(
        "/api/v1/admin/status",
        signal,
        5_000,
      );
      const supportingRequests = Promise.all([
        fetchJSONWithTimeout<DashboardData>("/api/v1/snapshot", signal),
        fetchJSONWithTimeout<QualitySample>(qualityArticlesURL, signal),
        fetchJSONWithTimeout<ArticleQualitySummary>(qualitySummaryURL, signal),
      ]);

      const nextStatus = await statusRequest;
      if (signal?.aborted) return;

      let live = false;
      if (nextStatus?.service && nextStatus.refresh) {
        setAdminStatus(nextStatus);
        setAdminStatusAvailability("ready");
        live = true;
      } else {
        // Never retain a previous Go result when the live status endpoint fails.
        setAdminStatus(null);
        setAdminStatusAvailability("offline");
      }

      const [nextData, nextQuality, nextQualitySummary] = await supportingRequests;
      if (signal?.aborted) return;
      if (nextData?.snapshot && nextData.forecast) {
        setDashboardData(nextData);
        live = true;
      }
      if (nextQuality?.articles) {
        setQualitySample((current) => {
          if (!current) return nextQuality;
          const locallySaved = new Map(
            current.articles
              .filter(hasDetailedArticleReview)
              .map((article) => [article.article_id, article]),
          );
          return {
            ...nextQuality,
            articles: nextQuality.articles.map((article) => {
              const saved = locallySaved.get(article.article_id);
              return saved?.decision && saved.decision_schema_version === 2
                ? {
                    ...article,
                    decision: saved.decision,
                    decision_schema_version: 2,
                    review_protocol_version: saved.review_protocol_version,
                    review_basis: saved.review_basis,
                    headline_support: saved.headline_support,
                    no_signal_reason: saved.no_signal_reason,
                    uncertainty_reason: saved.uncertainty_reason,
                    impact_flags: saved.impact_flags,
                    context_flags: saved.context_flags,
                    reviewed_at: saved.reviewed_at,
                    tags: saved.tags,
                  }
                : article;
            }),
          };
        });
      }
      if (nextQualitySummary) setQualitySummary(nextQualitySummary);
      setConnection(live ? "ready" : "offline");
    } finally {
      requestInFlight.current = false;
      if (!signal?.aborted) setChecking(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const initialCheck = window.setTimeout(() => void refreshAdmin(controller.signal), 0);
    const interval = window.setInterval(() => void refreshAdmin(controller.signal), 60_000);
    return () => {
      controller.abort();
      window.clearTimeout(initialCheck);
      window.clearInterval(interval);
    };
  }, [refreshAdmin]);

  useEffect(() => {
    if (qualityNotice?.kind !== "success") return;
    const timeout = window.setTimeout(() => setQualityNotice(null), 6_500);
    return () => window.clearTimeout(timeout);
  }, [qualityNotice]);

  useEffect(() => {
    if (!focusAfterReview.current || qualityNotice?.kind !== "success") return;
    focusAfterReview.current = false;
    const nextReviewButton = qualityGridRef.current?.querySelector<HTMLButtonElement>(
      "[data-review-start]:not(:disabled)",
    );
    (nextReviewButton ?? qualityNoticeRef.current)?.focus();
  }, [qualityNotice, qualitySample]);

  const refreshQualitySummary = async () => {
    try {
      const response = await fetch(qualitySummaryURL, { cache: "no-store" });
      if (response.ok) setQualitySummary(await response.json() as ArticleQualitySummary);
    } catch {
      // The answer is already saved; a delayed progress refresh must not report a false failure.
    }
  };

  const getArticleReviewDraft = (article: QualityArticle) => (
    articleReviewDrafts[article.article_id] ?? buildArticleReviewDraft(article)
  );

  const updateArticleReviewDraft = (
    article: QualityArticle,
    update: (draft: ArticleReviewDraft) => ArticleReviewDraft,
  ) => {
    setArticleReviewDrafts((current) => ({
      ...current,
      [article.article_id]: update(current[article.article_id] ?? buildArticleReviewDraft(article)),
    }));
  };

  const selectReviewBasis = (article: QualityArticle, reviewBasis: ReviewBasis) => {
    updateArticleReviewDraft(article, (draft) => {
      const decision = reviewBasis === "unavailable" && draft.decision !== "uncertain"
        ? undefined
        : draft.decision;
      return {
        ...draft,
        reviewBasis,
        decision,
        headlineSupport: reviewBasis === "headline_only" && isResolvedArticleDecision(decision)
          ? "sufficient"
          : undefined,
        noSignalReason: decision === "not_flood_related" ? draft.noSignalReason : undefined,
        uncertaintyReason: decision === "uncertain" ? draft.uncertaintyReason : undefined,
      };
    });
  };

  const selectArticleDecision = (article: QualityArticle, decision: ArticleDecision) => {
    updateArticleReviewDraft(article, (draft) => {
      if (!draft.reviewBasis || (draft.reviewBasis === "unavailable" && decision !== "uncertain")) return draft;
      return {
        ...draft,
        decision,
        headlineSupport: isResolvedArticleDecision(decision)
          ? draft.reviewBasis === "headline_only" ? "sufficient" : draft.headlineSupport
          : undefined,
        noSignalReason: decision === "not_flood_related" ? draft.noSignalReason : undefined,
        uncertaintyReason: decision === "uncertain" ? draft.uncertaintyReason : undefined,
      };
    });
  };

  const toggleImpactFlag = (article: QualityArticle, value: ImpactFlag) => {
    updateArticleReviewDraft(article, (draft) => ({
      ...draft,
      impactFlags: draft.impactFlags.includes(value)
        ? draft.impactFlags.filter((flag) => flag !== value)
        : [...draft.impactFlags, value],
    }));
  };

  const toggleContextFlag = (article: QualityArticle, value: ContextFlag) => {
    updateArticleReviewDraft(article, (draft) => ({
      ...draft,
      contextFlags: draft.contextFlags.includes(value)
        ? draft.contextFlags.filter((flag) => flag !== value)
        : [...draft.contextFlags, value],
    }));
  };

  const beginArticleReviewCorrection = (article: QualityArticle) => {
    setArticleReviewDrafts((current) => ({
      ...current,
      [article.article_id]: buildArticleReviewDraft(article),
    }));
    setEditingArticleID(article.article_id);
    setQualityNotice(null);
  };

  const cancelArticleReviewCorrection = (article: QualityArticle) => {
    setEditingArticleID(null);
    setArticleReviewDrafts((current) => {
      const next = { ...current };
      delete next[article.article_id];
      return next;
    });
  };

  const saveArticleReview = async (article: QualityArticle) => {
    const draft = getArticleReviewDraft(article);
    if (!isArticleReviewDraftComplete(draft) || !draft.decision || !draft.reviewBasis) {
      setQualityNotice({ kind: "error", message: t("completeRequiredReviewFields") });
      return;
    }
    if (reviewRequestInFlight.current) return;
    reviewRequestInFlight.current = true;
    const decision = draft.decision;
    setSavingArticleReview({ articleID: article.article_id, decision });
    setQualityNotice(null);
    let sampleChanged = false;
    try {
      const response = await fetch(qualityArticlesURL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          article_id: article.article_id,
          decision,
          review_protocol_version: 1,
          review_basis: draft.reviewBasis,
          headline_support: isResolvedArticleDecision(decision) ? draft.headlineSupport : undefined,
          no_signal_reason: decision === "not_flood_related" ? draft.noSignalReason : undefined,
          uncertainty_reason: decision === "uncertain" ? draft.uncertaintyReason : undefined,
          impact_flags: draft.impactFlags,
          context_flags: draft.contextFlags,
        }),
      });
      if (!response.ok) {
        sampleChanged = response.status === 400;
        throw new Error(`Article review API returned ${response.status}`);
      }
      const payload = await response.json() as ArticleReviewResponse;
      if (
        payload.review.article_id !== article.article_id
        || payload.review.decision !== decision
        || payload.review.decision_schema_version !== 2
        || payload.review.review_protocol_version !== 1
        || payload.review.review_basis !== draft.reviewBasis
      ) {
        throw new Error("Article review API returned an unexpected answer");
      }
      focusAfterReview.current = true;
      setQualitySample((current) => current ? {
        ...current,
        articles: current.articles.map((item) => item.article_id === article.article_id
          ? {
            ...item,
            decision: payload.review.decision,
            decision_schema_version: payload.review.decision_schema_version,
            review_protocol_version: payload.review.review_protocol_version,
            review_basis: payload.review.review_basis,
            headline_support: payload.review.headline_support,
            no_signal_reason: payload.review.no_signal_reason,
            uncertainty_reason: payload.review.uncertainty_reason,
            impact_flags: payload.review.impact_flags ?? [],
            context_flags: payload.review.context_flags ?? [],
            reviewed_at: payload.review.reviewed_at,
          }
          : item),
      } : current);
      setArticleReviewDrafts((current) => ({
        ...current,
        [article.article_id]: {
          reviewBasis: payload.review.review_basis,
          decision: payload.review.decision,
          headlineSupport: payload.review.headline_support,
          noSignalReason: payload.review.no_signal_reason,
          uncertaintyReason: payload.review.uncertainty_reason,
          impactFlags: payload.review.impact_flags ?? [],
          contextFlags: payload.review.context_flags ?? [],
        },
      }));
      setEditingArticleID(null);
      const decisionMetadata = getArticleReviewOption(decision);
      const decisionLabel = decisionMetadata ? t(decisionMetadata.labelKey) : decision;
      const pendingAfterSave = Math.max(0, pendingQualityArticles.length - (hasDetailedArticleReview(article) ? 0 : 1));
      const remainingCopy = pendingAfterSave === 0
        ? t("noQueueRemaining")
        : pendingAfterSave === 1
          ? t("oneQueueRemaining")
          : t("manyQueueRemaining", { count: formatNumber(pendingAfterSave, localeTag) });
      setQualityNotice({
        kind: "success",
        message: decisionMetadata?.resolved === false
          ? t("savedUncertain", { decision: decisionLabel, remaining: remainingCopy })
          : t("savedResolved", { decision: decisionLabel, remaining: remainingCopy }),
      });
      void refreshQualitySummary();
    } catch {
      setQualityNotice({
        kind: "error",
        message: sampleChanged
          ? t("sampleChanged")
          : t("saveFailed"),
      });
    } finally {
      reviewRequestInFlight.current = false;
      setSavingArticleReview(null);
      if (sampleChanged) void refreshAdmin();
    }
  };

  const modelReady = forecast.model.status === "ready";
  const refreshHealthy = adminStatusAvailability === "ready" && adminStatus?.refresh.health === "healthy";
  const overallStatus = refreshHealthy && modelReady
    ? t("operatingNormally")
    : adminStatusAvailability === "offline"
      ? t("operationsStatusUnavailable")
      : t("attentionNeeded");
  const resolvedReviews = qualitySummary?.resolved_reviews ?? 0;
  const minimumReviews = qualitySummary?.minimum_sample ?? 20;
  const remainingReviews = qualitySummary?.remaining_to_sample ?? Math.max(0, minimumReviews - resolvedReviews);
  const qualitySampleReady = qualitySummary?.status === "sample_ready";
  const qualityBalancePending = !qualitySampleReady && remainingReviews === 0;
  const qualityProgress = minimumReviews > 0
    ? Math.min(100, (resolvedReviews / minimumReviews) * 100)
    : 0;
  const queueReadinessComputed = queueSelectionIntent?.readiness_status === "computed";
  const liveAdminStatus = adminStatusAvailability === "ready" ? adminStatus : null;
  const soak = liveAdminStatus?.refresh.soak ?? null;
  const backup = liveAdminStatus?.backup ?? null;
  const pilotReadiness = liveAdminStatus?.pilot_readiness ?? null;
  const readinessAvailable = Boolean(soak && backup && pilotReadiness);
  const readyForPilotSetup = Boolean(
    readinessAvailable
      && soak?.status === "passed"
      && !soak.current_stale
      && backup?.status === "verified"
      && pilotReadiness?.status === "ready_for_pilot_setup"
      && pilotReadiness.local_reliability_passed
      && pilotReadiness.backup_verified,
  );
  const resetReasonPresent = Boolean(
    soak?.reset_reason
      && soak.reset_reason !== "none"
      && soak.reset_reason !== "not_started",
  );
  const checkRestarted = Boolean(
    readinessAvailable
      && !readyForPilotSetup
      && soak?.status !== "passed"
      && (soak?.status === "failed" || soak?.last_reset_at || resetReasonPresent),
  );
  const refreshEvidenceBlocked = Boolean(
    pilotReadiness?.blockers.some(
      (blocker) => blocker === "refresh_stale"
        || blocker === "refresh_unhealthy"
        || blocker === "soak_evidence_mismatch",
    ),
  );
  const readinessDecision = !readinessAvailable
    ? adminStatusAvailability === "loading" ? t("checkingReadiness") : t("statusUnavailable")
    : readyForPilotSetup
      ? t("goPrivatePilot")
      : checkRestarted
        ? t("checkRestarted")
        : t("keepObserving");
  const readinessTone = !readinessAvailable
    ? "unavailable"
    : readyForPilotSetup
      ? "ready"
      : checkRestarted
        ? "restarted"
        : "observing";
  const readinessHeading = !readinessAvailable
    ? adminStatusAvailability === "loading"
      ? t("checkingReliabilityRecord")
      : t("readinessUnavailableHeading")
    : readyForPilotSetup
      ? t("reliabilityPassed")
      : checkRestarted
        ? t("reliabilityRestarted")
        : refreshEvidenceBlocked
          ? t("latestCollectionAttention")
        : soak?.status === "not_started"
          ? t("firstRefreshStartsClock")
          : soak?.status === "passed"
            ? t("backupStillOpen")
            : t("keepComputerRunning");
  const readinessSummary = !readinessAvailable
    ? t("noGoWithoutStatus")
    : readyForPilotSetup
      ? t("readyForPrivateSetup")
      : checkRestarted
        ? t("restartedSummary")
        : refreshEvidenceBlocked
          ? t("evidenceFailClosed")
        : soak?.status === "not_started"
          ? t("noElapsedBeforeRefresh")
          : soak?.status === "passed"
            ? t("backupRequired")
            : t("progressWhileRunning");
  const soakProgress = readinessAvailable ? clampPercent(soak?.progress_percent) : 0;
  const expectedRuns = safeCount(soak?.expected_runs);
  const successfulRuns = safeCount(soak?.successful_runs);
  const coveredIntervals = Math.min(successfulRuns, expectedRuns);
  const failedRuns = safeCount(soak?.failed_runs);
  const missedRuns = safeCount(soak?.missed_runs);
  const interruptedRuns = safeCount(soak?.interrupted_runs);
  const problemRuns = failedRuns + missedRuns + interruptedRuns;
  const coverageLabel = readinessAvailable && expectedRuns > 0
    ? `${new Intl.NumberFormat(localeTag, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(clampPercent(soak?.coverage_percent))}%`
    : t("waiting");
  const freshnessLabel = !readinessAvailable || !soak?.last_observed_at
    ? t("waiting")
    : soak.current_stale
      ? t("stale")
      : t("current");
  const backupLabel = !readinessAvailable
    ? t("unavailable")
    : backup?.status === "verified"
      ? safeCount(backup.age_hours) >= 26 ? t("outOfDate") : t("verified")
      : backup?.status === "failed"
        ? t("failed")
        : t("notChecked");
  const readinessBlockerKeys: Record<string, MessageKey> = {
    soak_not_started: "blockerSoakNotStarted",
    soak_in_progress: "blockerSoakInProgress",
    soak_failed: "blockerSoakFailed",
    soak_evidence_mismatch: "blockerEvidenceMismatch",
    refresh_stale: "blockerRefreshStale",
    refresh_unhealthy: "blockerRefreshUnhealthy",
    coverage_below_target: "blockerCoverage",
    backup_not_verified: "blockerBackupNotVerified",
    backup_failed: "blockerBackupFailed",
    backup_too_old: "blockerBackupOld",
    local_reliability_not_passed: "blockerReliability",
    local_reliability: "blockerReliability",
    verified_backup: "blockerBackupNotVerified",
  };
  const readinessBlockers = Array.from(new Set(
    (pilotReadiness?.blockers ?? []).map(
      (blocker) => t(readinessBlockerKeys[blocker] ?? "blockerFallback"),
    ),
  )).slice(0, 3);
  const refreshStatusMessage = !adminStatus
    ? t("statusUnavailable")
    : adminStatus.refresh.status === "running"
      ? t("refreshRunning")
      : adminStatus.refresh.status === "success"
        ? t("refreshCompleted")
        : t("refreshNeedsAttention");
  const modelPredictions = new Map(
    forecast.model.pending_predictions.map((prediction) => [
      `${prediction.region_code}|${prediction.window_start}`,
      prediction,
    ]),
  );

  return (
    <main className="admin-page">
      <header className="site-header">
        <Link className="brand" href="/" aria-label={t("brandHome")}>
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </Link>
        <nav className="header-nav" aria-label={t("primaryNavigation")}>
          <Link href="/">{t("dashboard")}</Link>
          <Link className="active" href="/admin">{t("admin")}</Link>
          <Link href="/admin/training-data">{t("trainingData")}</Link>
        </nav>
        <div className="header-meta">
          <span className={connection === "ready" ? "live-dot" : "live-dot snapshot"} aria-hidden="true" />
          {connection === "ready" ? t("liveOperations") : connection === "loading" ? t("checkingOperations") : t("verifiedSnapshot")}
          <strong>{formatEastern(snapshot.window_end, localeTag)}</strong>
        </div>
        <LanguageSwitcher />
      </header>

      <nav className="mobile-section-nav" aria-label={t("adminSections")}>
        <a href="#status">{t("status")}</a>
        <a href="#operations">{t("operations")}</a>
        <a href="#admin-forecast">{t("forecasts")}</a>
        <a href="#article-quality">{t("quality")}</a>
        <Link href="/admin/training-data">{t("trainingData")}</Link>
      </nav>

      <section className="admin-hero" id="status">
        <div className="admin-hero-copy">
          <p className="eyebrow">{t("operationsConsole")}</p>
          <h1>{t("heroTitle")}</h1>
          <p>{t("heroDescription")}</p>
        </div>
        <aside className={`admin-health ${refreshHealthy ? "healthy" : "attention"}`} aria-label={t("currentSystemHealth")}>
          <span><i className="admin-status-dot" /> {t("currentStatus")}</span>
          <strong>{overallStatus}</strong>
          <p>
            {adminStatus
              ? t("lastSuccessfulRefresh", { time: formatEastern(adminStatus.refresh.last_success_at, localeTag) })
              : t("latestRetainedData", { time: formatEastern(snapshot.window_end, localeTag) })}
            {" "}{t("easternTime")}
          </p>
          <button className="admin-check-button" disabled={checking} onClick={() => void refreshAdmin()} type="button">
            {checking ? t("checking") : t("checkNow")}
          </button>
        </aside>
      </section>

      <section className="admin-summary" aria-label={t("operationsSummary")}>
        <article>
          <span>{t("refreshHealth")}</span>
          <strong>{adminStatus ? `${formatNumber(adminStatus.refresh.age_minutes, localeTag)}m` : "—"}</strong>
          <small>{refreshHealthy ? t("sinceLastSuccess") : t("waitingForLiveStatus")}</small>
        </article>
        <article>
          <span>{t("openForecasts")}</span>
          <strong>{formatNumber(forecast.pending_predictions.length, localeTag)}</strong>
          <small>{t("futureOutcomesCollecting")}</small>
        </article>
        <article>
          <span>{t("articleReviews")}</span>
          <strong>{formatNumber(resolvedReviews, localeTag)}/{formatNumber(minimumReviews, localeTag)}</strong>
          <small>{qualitySampleReady ? t("balancedRatesUnlocked") : qualityBalancePending ? t("reviewBalanceNeeded") : t("reviewMinimumRemaining", { count: formatNumber(remainingReviews, localeTag) })}</small>
        </article>
        <article>
          <span>{t("modelHoldout")}</span>
          <strong>{formatNumber(forecast.model.test_hours, localeTag)}h</strong>
          <small>{t("laterRows", { count: formatNumber(forecast.model.test_rows, localeTag) })}</small>
        </article>
      </section>

      <section className="admin-overview" id="operations">
        <article className="admin-surface">
          <div className="admin-section-heading">
            <div><p className="eyebrow">{t("operatingChecks")}</p><h2>{t("liveSystemChecklist")}</h2></div>
            <span className={refreshHealthy ? "admin-pill ready" : "admin-pill"}>{refreshHealthy ? t("healthy") : t("checkStatus")}</span>
          </div>
          <p>{t("controlsReadOnly")}</p>
          <ul className="admin-checks">
            <li><i className={connection === "ready" ? "" : "waiting"} /><strong>{t("localApi")}</strong><span>{connection === "ready" ? t("connected") : t("snapshotFallback")}</span></li>
            <li><i className={refreshHealthy ? "" : "waiting"} /><strong>{t("dataRefresh")}</strong><span>{refreshStatusMessage}</span></li>
            <li><i /><strong>{t("dashboardSnapshot")}</strong><span>{formatEastern(snapshot.window_end, localeTag)}</span></li>
            <li><i className={modelReady ? "" : "waiting"} /><strong>{t("chronologicalModel")}</strong><span>{modelReady ? t("benchmarkReady") : t("unavailable")}</span></li>
            <li><i className={qualitySampleReady ? "" : "waiting"} /><strong>{t("articleFilterEvaluation")}</strong><span>{t("resolvedOf", { resolved: formatNumber(resolvedReviews, localeTag), minimum: formatNumber(minimumReviews, localeTag) })}</span></li>
          </ul>
          <div className="admin-detail-grid">
            <div><span>{t("nextRefreshExpected")}</span><strong>{adminStatus ? formatEastern(adminStatus.refresh.expected_next_refresh_at, localeTag) : "—"}</strong></div>
            <div><span>{t("filesProcessed")}</span><strong>{adminStatus ? formatNumber(adminStatus.refresh.processed_files, localeTag) : "—"}</strong></div>
            <div>
              <span>{t("permanentArchive")}</span>
              <strong>{adminStatus?.refresh.archived_articles !== undefined ? formatNumber(adminStatus.refresh.archived_articles, localeTag) : "—"}</strong>
              <small>{adminStatus ? t("archiveRunDetails", { bytes: formatBytes(adminStatus.refresh.article_archive_bytes, localeTag), count: formatNumber(adminStatus.refresh.new_archived_articles ?? 0, localeTag) }) : t("preservedBeforeRotation")}</small>
              <small>{adminStatus ? t("titleBackfillDetails", { added: formatNumber(adminStatus.refresh.title_backfill_updated_articles ?? 0, localeTag), remaining: formatNumber(adminStatus.refresh.title_backfill_remaining_articles ?? 0, localeTag) }) : t("titleBackfillPending")}</small>
            </div>
            <div>
              <span>{t("rawArchiveUsage")}</span>
              <strong>{adminStatus ? `${formatBytes(adminStatus.refresh.retained_raw_bytes, localeTag)} / ${formatBytes(adminStatus.refresh.raw_storage_limit_bytes, localeTag)}` : "—"}</strong>
              <small>{adminStatus ? t("filesRetained", { count: formatNumber(adminStatus.refresh.retained_raw_files, localeTag) }) : t("storageBudget")}</small>
            </div>
          </div>
        </article>

        <aside
          className={`admin-surface admin-readiness ${readinessTone}`}
          aria-labelledby="pilot-readiness-heading"
        >
          <div className="admin-section-heading readiness-heading">
            <p className="eyebrow">{t("reliabilityCheck")}</p>
            <span
              className={`admin-pill readiness-decision ${readinessTone}`}
              aria-live="polite"
              aria-atomic="true"
            >
              {readinessDecision}
            </span>
          </div>
          <h2 id="pilot-readiness-heading">{readinessHeading}</h2>
          <p className="readiness-summary">{readinessSummary}</p>

          <div className="readiness-progress">
            <div className="readiness-timing" id="pilot-readiness-timing">
              <strong>{readinessAvailable ? t("observed", { duration: formatDuration(soak?.observed_minutes, localeTag) }) : "—"}</strong>
              <span>{readinessAvailable ? t("remaining", { duration: formatDuration(soak?.remaining_minutes, localeTag) }) : t("waitingForLiveStatus")}</span>
            </div>
            <progress
              aria-label={t("reliabilityProgress")}
              aria-describedby="pilot-readiness-timing"
              max={100}
              value={soakProgress}
            >
              {formatNumber(Math.round(soakProgress), localeTag)}%
            </progress>
            <small>{readinessAvailable ? t("windowComplete", { percent: formatNumber(Math.round(soakProgress), localeTag) }) : t("progressUnavailable")}</small>
          </div>

          <dl className="readiness-metrics">
            <div>
              <dt>{t("refreshSuccessRate")}</dt>
              <dd>{coverageLabel}</dd>
              <small>
                {readinessAvailable && expectedRuns > 0
                  ? t("intervalsCovered", { covered: formatNumber(coveredIntervals, localeTag), expected: formatNumber(expectedRuns, localeTag) })
                  : t("waitingFirstRefresh")}
              </small>
            </div>
            <div>
              <dt>{t("recordedProblems")}</dt>
              <dd>{readinessAvailable ? formatNumber(problemRuns, localeTag) : "—"}</dd>
              <small>{readinessAvailable ? t("problemTotals", { failed: formatNumber(failedRuns, localeTag), missed: formatNumber(missedRuns, localeTag), interrupted: formatNumber(interruptedRuns, localeTag) }) : t("failureTotalsUnavailable")}</small>
            </div>
            <div>
              <dt>{t("currentFreshness")}</dt>
              <dd className={soak?.current_stale ? "attention" : ""}>{freshnessLabel}</dd>
              <small>
                {readinessAvailable && soak?.last_observed_at
                  ? <>{formatMessage(pageMessages.lastCompleted, { time: "" }).trim()} <time dateTime={soak.last_observed_at}>{formatEastern(soak.last_observed_at, localeTag)}</time></>
                  : t("noCompletedRefresh")}
              </small>
            </div>
            <div>
              <dt>{t("safetyBackup")}</dt>
              <dd className={backup?.status === "failed" || (backup?.status === "verified" && safeCount(backup.age_hours) >= 26) ? "attention" : ""}>{backupLabel}</dd>
              <small>
                {readinessAvailable && backup?.status === "verified" && backup.verified_at
                  ? <>{formatMessage(pageMessages.backupVerifiedAt, { time: "" }).trim()} <time dateTime={backup.verified_at}>{formatEastern(backup.verified_at, localeTag)}</time>{backup.age_hours !== null ? t("backupAge", { hours: formatNumber(safeCount(backup.age_hours), localeTag) }) : ""}</>
                  : backup?.status === "failed"
                    ? t("backupCheckFailed")
                    : t("backupNotConfirmed")}
              </small>
            </div>
          </dl>

          {!readyForPilotSetup && readinessBlockers.length > 0 ? (
            <ul className="readiness-blockers" aria-label={t("openReadinessChecks")}>
              {readinessBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
            </ul>
          ) : null}
          <p className="readiness-scope">{t("readinessScope")}</p>
        </aside>
      </section>

      <section className="admin-forecast-section" id="admin-forecast" aria-labelledby="admin-forecast-heading">
        <div className="admin-section-heading">
          <div>
            <p className="eyebrow">{t("forecastOperations")}</p>
            <h2 id="admin-forecast-heading">{t("forecastHeading")}</h2>
          </div>
          <span className="admin-pill ready">{t("readOnly")}</span>
        </div>
        <div className="admin-forecast-grid">
          <article className="admin-surface admin-forecast-table">
            {forecast.pending_predictions.length > 0 ? (
              <div className="admin-table-wrap">
                <table className="admin-forecast-mobile-table">
                  <thead><tr><th>{t("region")}</th><th>{t("detected")}</th><th>{t("outcomeCloses")}</th><th>{t("remainingColumn")}</th><th>{t("modelScore")}</th></tr></thead>
                  <tbody>
                    {forecast.pending_predictions.map((prediction) => {
                      const modelPrediction = modelPredictions.get(`${prediction.region_code}|${prediction.window_start}`);
                      return (
                        <tr key={`${prediction.region_code}|${prediction.window_start}`}>
                          <td data-label={t("region")}><strong>{prediction.region_code}</strong><small>{t("storiesDomains", {
                            stories: formatNumber(prediction.stories_at_detection, localeTag),
                            storyUnit: t(prediction.stories_at_detection === 1 ? "story" : "stories"),
                            domains: formatNumber(prediction.domains_at_detection, localeTag),
                            domainUnit: t(prediction.domains_at_detection === 1 ? "domain" : "domains"),
                          })}</small></td>
                          <td data-label={t("detected")}>{formatEastern(prediction.window_start, localeTag)}</td>
                          <td data-label={t("outcomeCloses")}>{formatEastern(prediction.matures_at, localeTag)}</td>
                          <td data-label={t("remainingColumn")}><span className="admin-countdown">{formatNumber(prediction.hours_remaining, localeTag)}h</span></td>
                          <td data-label={t("modelScore")}>{modelPrediction ? `${new Intl.NumberFormat(localeTag, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(modelPrediction.model_score * 100)} / 100` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : <p className="admin-empty">{t("noPendingForecasts")}</p>}
          </article>

          <aside className="admin-model-card">
            <span>{t("laterHoldout")}</span>
            <strong>{formatPercent(forecast.model.test_metrics.average_precision, localeTag)}</strong>
            <small>{t("averagePrecision")}</small>
            <dl>
              <div><dt>{t("alertPrecision")}</dt><dd>{formatPercent(forecast.model.test_metrics.precision, localeTag)}</dd></div>
              <div><dt>{t("outcomeRecall")}</dt><dd>{formatPercent(forecast.model.test_metrics.recall, localeTag)}</dd></div>
              <div><dt>{t("falseAlertsDay")}</dt><dd>{forecast.model.test_metrics.false_alerts_per_day === null || forecast.model.test_metrics.false_alerts_per_day === undefined ? "—" : new Intl.NumberFormat(localeTag, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(forecast.model.test_metrics.false_alerts_per_day)}</dd></div>
              <div><dt>{t("testPositives")}</dt><dd>{formatNumber(forecast.model.test_positives, localeTag)}</dd></div>
            </dl>
            <p>{t("benchmarkCaveat")}</p>
          </aside>
        </div>
      </section>

      <section className="admin-quality-section" id="article-quality" aria-labelledby="article-quality-heading">
        <div className="admin-section-heading admin-quality-heading">
          <div>
            <p className="eyebrow">{t("filterValidation")}</p>
            <h2 id="article-quality-heading">{t("qualityHeading")}</h2>
            <p>{t("qualityDescription")}</p>
          </div>
          <a className="export-link" download="crisispulse-article-quality-reviews.csv" href={qualityExportURL}>
            {t("downloadReviews")} <span aria-hidden="true">↓</span>
          </a>
        </div>

        {pendingQualityArticles.length === 0 ? <div className="admin-quality-overview">
          <article className="admin-review-progress">
            <div>
              <p className="eyebrow">{t("measurementProgress")}</p>
              <h3>{qualitySampleReady ? t("measurementsReady") : t("ratesLocked")}</h3>
            </div>
            <div className="admin-review-meter">
              <div><strong>{formatNumber(resolvedReviews, localeTag)}</strong><span>{t("resolvedLabels")}</span></div>
              <span className="admin-meter" role="progressbar" aria-label={t("resolvedProgress")} aria-valuemin={0} aria-valuemax={minimumReviews} aria-valuenow={resolvedReviews}><i style={{ width: `${qualityProgress}%` }} /></span>
              <small>{qualitySampleReady ? t("balancedMinimum") : qualityBalancePending ? t("totalMinimumBalance") : t("decisionsRemaining", { count: formatNumber(remainingReviews, localeTag) })}</small>
            </div>
          </article>
          <aside className="admin-quality-results">
            <div><span>{t("strongMatchRelevance")}</span><strong>{formatPercent(qualitySummary?.high_match_flood_related_rate, localeTag)}</strong><small>{t("strongResolved", { count: formatNumber(qualitySummary?.high_resolved ?? 0, localeTag) })}</small></div>
            <div><span>{t("blockedRelevance")}</span><strong>{formatPercent(qualitySummary?.weak_match_flood_related_rate, localeTag)}</strong><small>{t("blockedResolved", { count: formatNumber(qualitySummary?.weak_resolved ?? 0, localeTag) })}</small></div>
            <p>{t("qualityCaveat")}</p>
          </aside>
        </div> : null}

        <ol className="admin-quality-guide" aria-label={t("reviewGuide")}>
          <li><span>01</span><div><strong>{t("openPublisher")}</strong><small>{t("openPublisherHelp")}</small></div></li>
          <li><span>02</span><div><strong>{t("judgeFlooding")}</strong><small>{t("judgeFloodingHelp")}</small></div></li>
          <li><span>03</span><div><strong>{t("honestUncertainty")}</strong><small>{t("honestUncertaintyHelp")}</small></div></li>
        </ol>
        <p className="article-label-precedence" id="article-review-precedence">{t("labelPrecedence")}</p>

        {pendingQualityArticles.length === 0 ? <section className="article-training-labels" aria-labelledby="training-label-breakdown-heading">
          <div className="article-training-heading">
            <div>
              <p className="eyebrow">{t("measurementProgress")}</p>
              <h3 id="training-label-breakdown-heading">{t("trainingLabelBreakdown")}</h3>
              <p>{t("trainingLabelHelp")}</p>
            </div>
            {qualitySummary === null ? (
              <p className="legacy-review-note">{t("trainingCountsUnavailable")}</p>
            ) : safeCount(qualitySummary.legacy_reviews) > 0 ? (
              <p className="legacy-review-note">
                {safeCount(qualitySummary.legacy_reviews) === 1
                  ? t("oneLegacyExcluded")
                  : t("legacyExcluded", { count: formatNumber(safeCount(qualitySummary.legacy_reviews), localeTag) })}
              </p>
            ) : null}
          </div>
          <ol className="article-training-counts">
            {articleReviewOptions.map((option) => (
              <li className={option.tone} key={option.value}>
                <strong>{qualitySummary === null ? "—" : formatNumber(safeCount(qualitySummary[option.countField]), localeTag)}</strong>
                <span>{t(option.labelKey)}</span>
                <small id={`article-label-definition-${option.value}`}>{t(option.definitionKey)}</small>
              </li>
            ))}
          </ol>
        </section> : null}

        {qualityNotice ? (
          <p
            aria-atomic="true"
            className={`quality-review-notice ${qualityNotice.kind}`}
            ref={qualityNoticeRef}
            role={qualityNotice.kind === "error" ? "alert" : "status"}
            tabIndex={-1}
          >
            <strong>{qualityNotice.kind === "success" ? t("answerSaved") : t("notSaved")}</strong>
            <span>{qualityNotice.message}</span>
          </p>
        ) : null}

        {queueSelectionIntent && pendingQualityArticles.length === 0 ? (
          <aside className="smart-review-banner" aria-labelledby="smart-review-heading">
            <div>
              <p className="eyebrow">{t("smartQueueEyebrow")}</p>
              <h3 id="smart-review-heading">{t("smartQueueHeading")}</h3>
              <p>{queueReadinessComputed ? t("smartQueueDescription") : t("smartQueueUnavailable")}</p>
              <small>{t("smartQueueHint")}</small>
            </div>
            {queueReadinessComputed ? (
              <dl>
                <div>
                  <dt>{t("smartQueueReviewedRows")}</dt>
                  <dd>{formatNumber(queueSelectionIntent.usable_rows, localeTag)} / {formatNumber(queueSelectionIntent.usable_rows_minimum, localeTag)}</dd>
                </div>
                <div>
                  <dt>{t("smartQueueArticleDates")}</dt>
                  <dd>{formatNumber(queueSelectionIntent.distinct_article_dates, localeTag)} / {formatNumber(queueSelectionIntent.article_date_minimum, localeTag)}</dd>
                </div>
                <div>
                  <dt>{t("smartQueuePublishers")}</dt>
                  <dd>{formatNumber(queueSelectionIntent.publisher_groups, localeTag)} / {formatNumber(queueSelectionIntent.publisher_group_minimum, localeTag)}</dd>
                </div>
                <div>
                  <dt>{t("smartQueueInferenceText")}</dt>
                  <dd>{formatPercent(queueSelectionIntent.inference_text_coverage, localeTag)} / {formatPercent(queueSelectionIntent.inference_text_minimum, localeTag)}</dd>
                </div>
              </dl>
            ) : null}
          </aside>
        ) : null}

        {qualitySample?.articles?.length ? (
          <div className="quality-queue-toolbar">
            <p><strong>{formatNumber(pendingQualityArticles.length, localeTag)}</strong><span>{pendingQualityArticles.length === 1 ? t("oneNeedsReview") : t("manyNeedReview")}</span></p>
            {reviewedQualityArticles.length ? (
              <button
                aria-expanded={showReviewedArticles}
                onClick={() => setShowReviewedArticles((current) => !current)}
                type="button"
              >
                {showReviewedArticles ? t("hideReviewed") : t("showReviewed", { count: formatNumber(reviewedQualityArticles.length, localeTag) })}
              </button>
            ) : null}
          </div>
        ) : null}

        {qualitySample?.articles?.length && visibleQualityArticles.length ? (
          <div className="article-quality-grid" ref={qualityGridRef}>
            {visibleQualityArticles.map((article) => {
              const link = safeArticleURL(article.url);
              const isSaving = savingArticleReview?.articleID === article.article_id;
              const isReviewed = hasDetailedArticleReview(article);
              const isEditing = !isReviewed || editingArticleID === article.article_id;
              const draft = getArticleReviewDraft(article);
              const activeDecision = isEditing ? draft.decision : getDetailedArticleDecision(article);
              const draftComplete = isArticleReviewDraftComplete(draft);
              const resolvedClassesEnabled = Boolean(draft.reviewBasis && draft.reviewBasis !== "unavailable");
              const bucket = reviewBucketMetadata[article.review_bucket];
              const decisionStatus = getArticleDecisionStatus(article, isSaving);
              const titleSourceKey = getTitleSourceMessageKey(article.title_source);
              const selectionIntent = article.selection_intent;
              const savedBasis = reviewBasisOptions.find((option) => option.value === article.review_basis);
              const savedHeadlineSupport = headlineSupportOptions.find((option) => option.value === article.headline_support);
              const savedNoSignalReason = noSignalReasonOptions.find((option) => option.value === article.no_signal_reason);
              const savedUncertaintyReason = uncertaintyReasonOptions.find((option) => option.value === article.uncertainty_reason);
              const savedImpactFlags = impactFlagOptions.filter((option) => article.impact_flags?.includes(option.value));
              const savedContextFlags = contextFlagOptions.filter((option) => article.context_flags?.includes(option.value));
              return (
                <article
                  aria-busy={isSaving}
                  className={`article-quality-card${isSaving ? " saving" : ""}${hasDetailedArticleReview(article) ? " reviewed" : ""}${hasLegacyArticleReview(article) ? " legacy-review" : ""}`}
                  key={article.article_id}
                >
                  <header>
                    {isReviewed ? <span className={`quality-strength ${article.match_strength}`}>{t(bucket.labelKey)}</span> : <span />}
                    <span className={`decision-chip ${decisionStatus.tone}`}>
                      {t(decisionStatus.labelKey)}
                    </span>
                  </header>
                  {link ? <a className="article-quality-title" href={link} rel="noopener noreferrer" target="_blank">{article.title} <span aria-hidden="true">↗</span></a> : <strong className="article-quality-title">{article.title}</strong>}
                  <small className={`article-title-source ${article.title_source ?? "legacy"}`}>
                    {t(titleSourceKey)}
                  </small>
                  <dl>
                    <div><dt>{t("publisher")}</dt><dd>{article.source_domain || t("unknown")}</dd></div>
                    <div><dt>{t("location")}</dt><dd>{article.location_name || t("unassignedLocation")}</dd></div>
                    <div><dt>{t("seen")}</dt><dd>{formatEastern(article.seen_at, localeTag)}</dd></div>
                  </dl>
                  {isSaving ? <p className="article-review-state" role="status">{t("savingThisAnswer")}</p> : null}
                  {isReviewed && !isEditing ? (
                    <div className="article-review-readonly">
                      <strong>{t("reviewReadOnly")}</strong>
                      {!hasProtocolArticleReview(article) ? <p>{t("protocolMetadataMissing")}</p> : (
                        <dl className="review-protocol-summary">
                          {savedBasis ? <div><dt>{t("reviewStepOne")}</dt><dd>{t(savedBasis.labelKey)}</dd></div> : null}
                          {savedHeadlineSupport ? <div><dt>{t("headlineSupportQuestion")}</dt><dd>{t(savedHeadlineSupport.labelKey)}</dd></div> : null}
                          {savedNoSignalReason ? <div><dt>{t("noSignalReasonQuestion")}</dt><dd>{t(savedNoSignalReason.labelKey)}</dd></div> : null}
                          {savedUncertaintyReason ? <div><dt>{t("uncertaintyReasonQuestion")}</dt><dd>{t(savedUncertaintyReason.labelKey)}</dd></div> : null}
                        </dl>
                      )}
                      {savedImpactFlags.length || savedContextFlags.length ? (
                        <ul className="review-saved-flags">
                          {[...savedImpactFlags, ...savedContextFlags].map((option) => <li key={option.value}>{t(option.labelKey)}</li>)}
                        </ul>
                      ) : null}
                      {article.tags?.length ? (
                        <div className="legacy-review-tags"><strong>{t("legacyContextTags")}</strong><span>{article.tags.join(" · ")}</span></div>
                      ) : null}
                      <details className="article-audit-context">
                        <summary>{t("auditContext")}</summary>
                        <p>{t("auditContextHelp")}</p>
                        <div className="audit-match"><strong>{t(bucket.labelKey)}</strong><span>{t(bucket.reasonKey)}</span></div>
                        {article.themes.length || article.quality_flags.length ? (
                          <div><strong>{t("auditThemes")}</strong><div className="quality-theme-list">{[...article.themes, ...article.quality_flags].map((value) => <span key={value}>{value}</span>)}</div></div>
                        ) : null}
                        {selectionIntent ? (
                          <div className="article-selection-intent">
                            <span className="selection-rank">{t("samplingRank", { rank: selectionIntent.rank })}</span>
                            <strong>{t("auditSelection")}</strong>
                            {selectionIntent.sampling_split ? <em>{t("samplingWindow", { window: t(samplingSplitMessageKeys[selectionIntent.sampling_split]) })}</em> : null}
                            <span className="selection-reasons">{selectionIntent.reasons.map((reason) => <i key={reason}>{t(qualitySelectionReasonMessageKeys[reason])}</i>)}</span>
                          </div>
                        ) : null}
                      </details>
                      <button className="edit-review-button" disabled={savingArticleReview !== null} onClick={() => beginArticleReviewCorrection(article)} type="button">{t("editReview")}</button>
                    </div>
                  ) : (
                    <form className="article-review-form" onSubmit={(event) => { event.preventDefault(); void saveArticleReview(article); }}>
                      <fieldset className="review-protocol-step">
                        <legend>{t("reviewStepOne")}</legend>
                        <p>{t("reviewStepOneHelp")}</p>
                        <div className="review-choice-grid review-basis-grid">
                          {reviewBasisOptions.map((option, index) => (
                            <button
                              aria-pressed={draft.reviewBasis === option.value}
                              className={draft.reviewBasis === option.value ? "selected" : ""}
                              data-review-start={index === 0 ? "true" : undefined}
                              disabled={isSaving}
                              key={option.value}
                              onClick={() => selectReviewBasis(article, option.value)}
                              type="button"
                            ><strong>{t(option.labelKey)}</strong>{option.descriptionKey ? <small>{t(option.descriptionKey)}</small> : null}</button>
                          ))}
                        </div>
                      </fieldset>

                      <fieldset className="review-protocol-step">
                        <legend>{t("reviewStepTwo")}</legend>
                        <p>{t("reviewStepTwoHelp")}</p>
                        {!draft.reviewBasis ? <small className="review-required-hint">{t("chooseBasisFirst")}</small> : null}
                        <div className="review-actions" aria-describedby="article-review-precedence" aria-label={t("resolvedLabelsGroup")}>
                          {articleReviewOptions.filter((option) => option.resolved).map((option) => (
                            <button
                              aria-pressed={activeDecision === option.value}
                              className={`review-button ${option.tone}${activeDecision === option.value ? " selected" : ""}`}
                              disabled={isSaving || !resolvedClassesEnabled}
                              key={option.value}
                              onClick={() => selectArticleDecision(article, option.value)}
                              type="button"
                            >
                              {activeDecision === option.value ? <span aria-hidden="true" className="review-selected-check">✓</span> : null}
                              <span><strong>{t(option.labelKey)}</strong><small>{t(option.definitionKey)}</small></span>
                            </button>
                          ))}
                        </div>
                        <div className="cannot-verify-choice">
                          <span>{t("cannotVerifyPrompt")}</span>
                          {articleReviewOptions.filter((option) => !option.resolved).map((option) => (
                            <button
                              aria-pressed={activeDecision === option.value}
                              className={`review-button ${option.tone}${activeDecision === option.value ? " selected" : ""}`}
                              disabled={isSaving || !draft.reviewBasis}
                              key={option.value}
                              onClick={() => selectArticleDecision(article, option.value)}
                              type="button"
                            >
                              {activeDecision === option.value ? <span aria-hidden="true" className="review-selected-check">✓</span> : null}
                              <span><strong>{t(option.labelKey)}</strong><small>{t(option.definitionKey)}</small></span>
                            </button>
                          ))}
                        </div>
                      </fieldset>

                      {draft.decision ? <fieldset className="review-protocol-step review-required-details">
                        <legend>{t("reviewStepThree")}</legend>
                        {isResolvedArticleDecision(draft.decision) && (draft.reviewBasis === "full_article" || draft.reviewBasis === "publisher_summary") ? (
                          <div className="review-detail-group"><strong>{t("headlineSupportQuestion")}</strong><div className="review-choice-grid">{headlineSupportOptions.map((option) => <button aria-pressed={draft.headlineSupport === option.value} className={draft.headlineSupport === option.value ? "selected" : ""} key={option.value} onClick={() => updateArticleReviewDraft(article, (current) => ({ ...current, headlineSupport: option.value }))} type="button"><strong>{t(option.labelKey)}</strong>{option.descriptionKey ? <small>{t(option.descriptionKey)}</small> : null}</button>)}</div></div>
                        ) : isResolvedArticleDecision(draft.decision) && draft.reviewBasis === "headline_only" ? <p className="review-automatic-detail">{t("headlineSupportAutomatic")}</p> : null}
                        {draft.decision === "not_flood_related" ? <div className="review-detail-group"><strong>{t("noSignalReasonQuestion")}</strong><div className="review-choice-grid">{noSignalReasonOptions.map((option) => <button aria-pressed={draft.noSignalReason === option.value} className={draft.noSignalReason === option.value ? "selected" : ""} key={option.value} onClick={() => updateArticleReviewDraft(article, (current) => ({ ...current, noSignalReason: option.value }))} type="button"><strong>{t(option.labelKey)}</strong>{option.descriptionKey ? <small>{t(option.descriptionKey)}</small> : null}</button>)}</div></div> : null}
                        {draft.decision === "uncertain" ? <div className="review-detail-group"><strong>{t("uncertaintyReasonQuestion")}</strong><div className="review-choice-grid compact">{uncertaintyReasonOptions.map((option) => <button aria-pressed={draft.uncertaintyReason === option.value} className={draft.uncertaintyReason === option.value ? "selected" : ""} key={option.value} onClick={() => updateArticleReviewDraft(article, (current) => ({ ...current, uncertaintyReason: option.value }))} type="button">{t(option.labelKey)}</button>)}</div></div> : null}
                      </fieldset> : null}

                      {draft.decision ? <details className="review-optional-details"><summary>{t("optionalEvidenceDetails")}</summary><p>{t("optionalEvidenceDetailsHelp")}</p><div className="review-flag-groups"><div><strong>{t("impactsReported")}</strong><div className="review-flag-grid">{impactFlagOptions.map((option) => <button aria-pressed={draft.impactFlags.includes(option.value)} className={draft.impactFlags.includes(option.value) ? "selected" : ""} key={option.value} onClick={() => toggleImpactFlag(article, option.value)} type="button">{t(option.labelKey)}</button>)}</div></div><div><strong>{t("storyContext")}</strong><div className="review-flag-grid">{contextFlagOptions.map((option) => <button aria-pressed={draft.contextFlags.includes(option.value)} className={draft.contextFlags.includes(option.value) ? "selected" : ""} key={option.value} onClick={() => toggleContextFlag(article, option.value)} type="button">{t(option.labelKey)}</button>)}</div></div></div></details> : null}

                      <div className="review-submit-actions">
                        {isReviewed ? <button className="cancel-review-button" disabled={isSaving} onClick={() => cancelArticleReviewCorrection(article)} type="button">{t("cancelCorrection")}</button> : null}
                        <button className="save-review-button" disabled={connection !== "ready" || savingArticleReview !== null || !draftComplete} type="submit">{isSaving ? t("saving") : isReviewed ? t("saveCorrection") : t("saveReview")}</button>
                      </div>
                      {draft.reviewBasis && draft.decision && !draftComplete ? <small className="review-required-hint">{t("completeRequiredReviewFields")}</small> : null}
                    </form>
                  )}
                </article>
              );
            })}
          </div>
        ) : qualitySample?.articles?.length || qualityQueueComplete ? (
          <div className="admin-surface quality-all-reviewed">
            <span aria-hidden="true">✓</span>
            <div><strong>{t("queueClear")}</strong><p>{t("queueClearHelp")}</p></div>
          </div>
        ) : (
          <div className="admin-surface admin-empty">{t("samplePending")}</div>
        )}

        <aside className="admin-quality-safety">
          <strong>{t("safeByDesign")}</strong>
          <span>{t("safetyDescription")}</span>
          <small>{qualitySample ? t("sampleDetails", {
            sampled: formatNumber(qualitySample.articles.length, localeTag),
            articleUnit: t(qualitySample.articles.length === 1 ? "article" : "articles"),
            archived: formatNumber(qualitySample.archive_articles, localeTag),
            recordUnit: t(qualitySample.archive_articles === 1 ? "record" : "records"),
            date: formatSampleDate(qualitySample.sample_date, localeTag),
          }) : t("waitingLiveSample")}</small>
        </aside>
      </section>
    </main>
  );
}
