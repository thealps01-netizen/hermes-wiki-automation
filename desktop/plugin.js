import {
  Badge, Button, ConfirmDialog, CopyButton, EmptyState, ErrorState, Input, Loader, PanelBlock,
  PanelDetail, PanelEmpty, PanelList, PanelListRow, PanelMeta, PanelSectionLabel, RowButton,
  SearchField, SegmentedControl, Tip, host, usePluginI18n
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const PLUGIN_ID = 'wiki-automation'
const ROUTE = '/wiki-automation'
const AREA_ROUTES = 'routes'
const AREA_SIDEBAR_NAV = 'sidebar.nav'
const PLURAL = new Intl.PluralRules()
const plural = (n, one, other) => (PLURAL.select(n) === 'one' ? one : other)

let ctxRef = null

const BUNDLES = {
  en: {
    wa: {
      title: 'Wiki Automation',
      deskLabel: 'Draft under review',
      deskLater: 'Later',
      deskMore: 'Show the change and the evidence',
      deskPosition: (k, n) => `${k} of ${n}`,
      deskPrevious: 'Previous draft',
      deskNext: 'Next draft',
      deskUnreadable: 'This draft could not be read, so it cannot be approved. You can reject it or leave it for later.',
      deskEngineFix: 'Updating the engine fixes this: open Settings and preview the update.',
      deskSavedAs: 'Will be saved as',
      metroAnd: (head, last) => `${head} and ${last}`,
      metroArrive: 'new drafts arrive here',
      metroAsk: 'Ask Hermes to fix these',
      metroAskDone: 'A new chat holds the request. Read it, then send it yourself.',
      metroAskHint: 'Writes a request into a new chat. You read it and send it yourself.',
      metroAskIntro: 'The daily wiki check found these problems. Please fix them in the wiki:',
      metroAskLine: 'Check output',
      metroAskNoChat: 'The chat box did not open. Start a new chat, then press again.',
      metroAskOutro: 'Fix only what is listed, and tell me what you changed.',
      metroBrings: 'What it brings',
      metroBringsText: name => `New ${name} conversations, read by the harvest and turned into wiki drafts.`,
      metroChangeTime: 'Change time',
      metroChecksUnread: 'The daily check could not be read',
      metroChooseFolder: 'Choose a wiki folder',
      metroClose: 'Close',
      metroCollecting: 'collecting now',
      metroCursor: 'Read up to',
      metroDailyCheck: 'Daily check',
      metroDailyCheckDoes: 'Reads the wiki and lists broken links, missing pages and stale notes.',
      metroDecide: 'you approve or reject',
      metroDrafts: n => plural(n, `${n} draft`, `${n} drafts`),
      metroDraftsWaiting: n => plural(n, `${n} draft waiting`, `${n} drafts waiting`),
      metroShort: {
        notIndexed: () => 'a retired index check',
        wikilink: d => (Number(d.n) === 1 ? '1 link is written as a path' : `${d.n ?? 'some'} links are written as paths`),
        dup: () => 'two pages share one name',
        drift: () => 'the three assistant setups differ',
        mirror: () => 'the backup mirror is behind',
        identity: () => 'the project id of the app changed',
        unresolvable: () => 'a link leads to a missing page',
        isolated: d => (Number(d.n) === 1 ? '1 page has no links' : `${d.n ?? 'some'} pages have no links`),
        pagesDown: () => 'the page count dropped',
        crash: () => 'a checker crashed',
        evidenceStore: () => 'the evidence store has problems',
        evidenceStale: () => 'some evidence is out of date',
        controlMissing: d => `${d.name ?? 'a control file'} is missing`,
        controlChanged: d => `${d.name ?? 'a control file'} differs from git`,
        controlTemplate: d => `${d.name ?? 'a control file'} was reset to a template`,
        projectFileMissing: () => 'the project file is missing',
        projectFileUnreadable: () => 'the project file cannot be read',
        projectReregistered: () => 'the app registered the folder again',
        indexStale: d => (Number(d.n) === 1 ? 'the index lists 1 missing page' : `the index lists ${d.n ?? 'some'} missing pages`),
        unsplitIngest: d => (Number(d.n) === 1 ? '1 page holds an unsplit ingest' : `${d.n ?? 'some'} pages hold an unsplit ingest`),
        mcpOff: () => 'MCP access is off',
        commitBacklog: d => (Number(d.n) === 1 ? '1 change is not committed' : `${d.n ?? 'some'} changes are not committed`),
        driftCrash: () => 'the setup check crashed',
        harvestUnread: d => (Number(d.n) === 1 ? '1 Codex session is not read' : `${d.n ?? 'some'} Codex sessions are not read`),
        harvestZstd: () => 'compressed Codex sessions cannot be read',
        engineCopies: () => 'old engine copies are in the data folder',
        other: () => 'an unrecognized problem'
      },
      metroDraftsText: 'Read each draft and approve it into the wiki, or reject it.',
      metroDraftsTitle: n => plural(n, 'A draft is waiting for your review', `${n} drafts are waiting for your review`),
      metroDraftsUnread: 'The drafts could not be read',
      metroEngineText: 'Open Settings to finish the engine install.',
      metroEngineUpdateText: (current, selected) => `This PC runs engine ${current}; this plugin ships ${selected}. Preview the update in Settings; nothing changes until you confirm.`,
      metroFailedPill: 'failed',
      metroFinishedIn: s => plural(s, 'finished in 1 second', `finished in ${s} seconds`),
      metroFolderText: 'Choose the folder the wiki lives in before anything can run.',
      metroFolderTitle: 'The wiki folder is not set',
      metroFound: 'found',
      metroFoundAt: (n, when) => plural(n, `1 problem found ${when}`, `${n} problems found ${when}`),
      metroFoundSince: (n, since) => plural(n, `1 problem since ${since}`, `${n} problems since ${since}`),
      metroGoodNext: next => `Nothing needs you. Next run ${next}.`,
      metroGoodText: 'Nothing needs you.',
      metroGoodTitle: 'Good service on the whole line',
      metroHarvest: 'Harvest',
      metroHarvestDoes: names => `Reads your ${names} conversations and writes drafts for you to review.`,
      metroHarvestDoesAny: 'Reads your conversations and writes drafts for you to review.',
      metroHarvestHead: 'Harvest station',
      metroHistory: 'History',
      metroHistoryEmpty: span => `No runs in the ${span}.`,
      metroHistoryOlder: 'Show older runs',
      metroHistoryAll: 'Show all runs',
      metroHistoryFull: 'Full technical log',
      metroHistoryFullHide: 'Hide technical log',
      metroHistoryCap: n => `Showing the newest ${n}. The full technical log has every run.`,
      metroHistoryRead: 'The run history could not be read.',
      metroLateMorning: (due, ran) => `The morning jobs were due at ${due} and ran at ${ran}.`,
      metroLateOne: (name, due, ran) => `${name} was due at ${due} and ran at ${ran}.`,
      metroDidHarvest: 'read your conversations',
      metroDidCheck: 'looked for problems',
      metroDidSources: 'let LLM Wiki read new sources',
      metroDidSave: 'saved wiki changes',
      metroRunFinished: 'finished',
      metroRunFinishedIn: s => `finished in ${s} s`,
      metroRunFound: n => plural(n, 'found 1 problem', `found ${n} problems`),
      metroRunRunningNow: 'running',
      metroRunFailedNow: 'failed',
      metroSpan24h: 'last 24 hours',
      metroSpan7d: 'last 7 days',
      metroSpanAll: 'whole history',
      metroWikiUnchecked: 'Not verified',
      metroFilesInPlace: (ok, total) => `${ok} of ${total} in place`,
      metroFilesMissing: names => `Missing: ${names}`,
      setNeedsYou: 'Needs you',
      setChangeTo: 'Change to',
      setFind: 'Find the wiki on this PC',
      setFindNote: 'Looks for folders that hold a wiki, if the one above moved.',
      setEngine: 'Engine',
      setEngineInto: 'Install into',
      metroPause: 'Pause',
      metroResume: 'Resume',
      metroHistoryHead: (span, n) => plural(n, `History · ${span} · 1 run`, `History · ${span} · ${n} runs`),
      metroHonest: 'A found folder does not prove every conversation was read.',
      metroHonestFrom: when => `Read up to ${when}.`,
      metroHvCannotRun: 'The harvest job cannot run',
      metroHvDoes: 'turns conversations into drafts',
      metroHvFailNoReason: 'No drafts were written.',
      metroHvFailReason: reason => `No drafts were written. Reason: ${reason}`,
      metroHvFailTitle: at => (at ? `Harvest stopped at ${at}` : 'Harvest stopped'),
      metroHvLastFailed: 'no drafts written',
      metroHvMissingTarget: 'Missing target',
      metroHvNoJob: 'Not created',
      metroHvNotVerified: 'Not verified',
      metroHvNoNext: 'No next run',
      metroHvPaused: 'The harvest is paused',
      metroHvReading: 'reading conversations',
      metroHvReads: (feeding, total) => `reads ${feeding} of ${total} lines`,
      metroHvSetUp: 'Set up the harvest',
      metroHvStarted: (at, rel) => (rel ? `started ${at}, ${rel}` : `started ${at}`),
      metroHvStopped: at => `stopped at ${at}`,
      metroIn: (h, m) => `in ${h} h ${m} min`,
      metroInMin: m => `in ${m} min`,
      metroJobCannotRun: name => `${name} cannot run`,
      metroJobFailed: name => `${name} failed`,
      metroJobMissing: name => `${name} is not set up`,
      metroJobMissingText: 'Open Settings to create the job.',
      metroLast: (when, result) => (result ? `Last run ${when} · ${result}` : `Last run ${when}`),
      metroLastRun: 'Last run',
      metroLine: 'Wiki line',
      metroLineClosed: name => `${name} line closed: folder not found`,
      metroLineHead: name => `${name} line`,
      metroLineMissing: 'folder not found',
      metroLineOff: 'off',
      metroLineOffState: 'Off — not collected',
      metroLineOnState: 'On — collected',
      metroLineOnMissing: 'On — nothing collected while the folder is missing',
      metroLineOnSkipped: 'On — skipped while the folder is missing; the other lines are read',
      metroLineUnread: 'could not be read',
      metroLineOnUnread: 'On — its history could not be read, so its conversations wait',
      metroLineUnreadTitle: name => `${name} line could not be read`,
      metroLinesUnreadTitle: names => `${names} lines could not be read`,
      metroLineUnreadText: others => (others
        ? `Their conversations wait for a later run; the other ${countWord(others)} ${others === 1 ? 'line was' : 'lines were'} read. The history format may have changed.`
        : 'Their conversations wait for a later run. The history format may have changed.'),
      metroLinesStopAll: 'This engine stops every line while a folder is missing, so no conversation is read. Updating the engine keeps the other lines running.',
      metroHvBlocked: 'stopped: a line folder is missing',
      metroHvNotFinished: 'The engine did not finish this run; its conversations wait for the next run.',
      metroHvCost: usd => `about $${usd} (Hermes' estimate)`,
      metroLineFolder: name => `${name} folder`,
      metroLinesClosed: names => `${names} lines closed: folders not found`,
      metroLineReading: 'reading',
      metroLineState: 'State',
      metroLineSub: 'from your conversations to your wiki',
      metroLinesUnread: 'The lines could not be read',
      metroMorning: 'Morning work',
      metroNeverRan: 'Never ran',
      metroNewSources: 'New sources',
      metroNewSourcesDoes: 'Looks for new files in raw/sources and adds them to the queue.',
      metroNext: at => `next ${at}`,
      metroNextAt: at => `next ${at}`,
      metroNextRun: 'Next run',
      metroNoCheck: 'no daily check yet',
      metroNoCheckText: 'The daily check has not reported. Its job may be missing or paused.',
      metroNoFolder: 'No folder',
      metroNoJobYet: 'No job yet',
      metroNoLines: 'No adapters reported',
      metroNoProblems: 'no problems',
      metroNoProblemsText: 'The last daily check found nothing to fix.',
      metroNoTimetable: 'no timetable',
      metroNotFound: 'not found',
      metroNotReported: 'not reported',
      metroOpenReview: 'Open review',
      metroOpenSettings: 'Open Settings',
      metroOwnerText: 'Approve or reject the owner decision before the harvest can continue.',
      metroOwnerTitle: 'A decision is waiting for you',
      metroPages: n => plural(n, '1 page', `${n} pages`),
      metroPagesUnknown: 'pages not reported',
      metroPausedNote: 'Paused — it will not run until you resume it.',
      metroPausedShort: 'Paused',
      metroPausedText: 'Resume it in the station when you want it to run again.',
      metroPausedTitle: name => `${name} is paused`,
      metroProblems: n => plural(n, '1 problem', `${n} problems`),
      metroProblemsMore: (named, more) => (more > 0 ? `${named} and ${more} more.` : `${named}.`),
      metroProblemsSince: (n, since) => plural(n, `1 wiki problem since ${since}`, `${n} wiki problems since ${since}`),
      metroProblemsTitle: n => plural(n, 'The wiki has 1 problem', `The wiki has ${n} problems`),
      metroRawLine: 'What the check said',
      metroReadFailed: what => `Could not read ${what}`,
      metroReadMore: n => plural(n, 'One more read failed.', `${n} more reads failed.`),
      metroReadTimetable: 'The timetable could not be read',
      metroReading: 'Reading…',
      metroReadingTimetable: 'Reading the timetable',
      metroResultFailed: 'failed',
      metroResultFound: n => plural(n, 'found 1 problem', `found ${n} problems`),
      metroResultOk: 'ok',
      metroResultUnknown: 'result not reported',
      metroReview: 'Your review',
      metroReviewDrafts: 'Review drafts',
      metroReviewHead: drafts => `Your review · ${drafts}`,
      metroReviewAt: (k, n) => `Your review · draft ${k} of ${n}`,
      metroUntouched: 'Your wiki and its jobs are untouched. Press Show the error to see what went wrong.',
      metroApproveAsk: 'Approve this draft?',
      metroApproveWrites: title => `“${title}” will be written to your wiki as`,
      metroApproveCredits: 'LLM Wiki may then use model credits to read it.',
      metroApproveEngine: 'Show what the engine reported',
      metroRunFailed: 'Failed',
      metroRunRunning: 'Running',
      metroRunningText: 'New drafts will wait at Your review. You can keep working.',
      metroRunningTitle: 'Harvest is reading your conversations',
      metroSaving: 'Saving',
      metroSavingDoes: 'Commits the wiki changes so nothing is lost.',
      metroSeeAlert: 'See the alert',
      metroSettings: 'Settings',
      metroSetupNeeded: 'Setup needed',
      metroShowError: 'Show the error',
      metroShowHarvest: 'Show the harvest',
      metroShowLine: 'Show the line',
      metroShowProblems: n => plural(n, 'Show the problem', `Show the ${n} problems`),
      metroShowWiki: 'Show the wiki',
      metroTimetable: 'Timetable',
      metroTryAgain: 'Try again',
      metroWaitingPill: n => `${n} waiting`,
      metroWhatChecks: 'Daily checks',
      metroWhatDrafts: 'Drafts',
      metroWhatEngine: 'Engine',
      metroWhatItDoes: 'What it does',
      metroWhatLines: 'Conversation lines',
      metroWhatRuns: 'Run history',
      metroWhatSettings: 'Settings',
      metroWiki: 'Wiki',
      metroConversations: 'Conversations',
      globeLabel: 'Your wiki',
      globeLead: (n, recent) => `${plural(n, '1 page', `${n} pages`)} · ${recent} changed this week`,
      globeAllFound: 'Every page your wiki links to exists.',
      globeMissingHead: n => plural(n, '1 page your wiki links to does not exist yet.',
        `${n} pages your wiki links to do not exist yet.`),
      globeHolders: k => plural(k, '1 page names them.', `${k} pages name them.`),
      globeNamedBy: k => plural(k, 'named by 1 page', `named by ${k} pages`),
      globeMore: n => plural(n, '1 more missing page', `${n} more missing pages`),
      globeMoreBy: 'named by other pages',
      globeKeyRecent: n => `changed this week · ${n}`,
      globeKeyOlder: n => `older · ${n}`,
      globeKeyNames: n => `names a missing page · ${n}`,
      globeKeyMissing: n => `missing page · ${n}`,
      globeBandWarn: n => `${n} name a missing page`,
      globeAge: d => (d === 0 ? 'changed today' : d === 1 ? 'changed yesterday' : `changed ${d} days ago`),
      globeNames: name => `names ${name}`,
      globeAria: (n, bands, recent, holders, missing) => `Your wiki as a sphere of ${n} dots, one per page, `
        + `banded by folder: ${bands}. ${recent} changed in the last 7 days. ${holders} pages name one of `
        + `${missing} missing pages, which float outside the sphere.`,
      globeReading: 'Reading your wiki pages…',
      globeUnread: 'Your wiki pages could not be read.',
      globeTruncated: n => `Only the first ${n} pages are drawn.`,
      globeDrag: 'Drag the sphere to turn it. Point at a dot to see its page.',
      metroWikiHead: pages => `Wiki · ${pages}`,
      metroWikiStation: 'Wiki station',
      folioDocument: 'Proposed change',
      folioDecision: 'Decision context',
      folioCollected: 'Source evidence',
      folioCandidateCreated: 'Candidate created',
      folioYourDecision: 'Your decision',
      folioPendingReview: 'Awaiting your review',
      folioDraft: 'Draft · approval required',
      folioProposal: 'Proposed change',
      folioReason: 'Reason & evidence',
      folioEvidenceCount: n => `${n} evidence ${plural(n, 'folder', 'folders')}`,
      candPublishWarning: 'Approval writes the source into raw/sources/. LLM Wiki ingestion may use model credits.',
      candFormatBlocked: 'Resolve the format problems before approval.',
      candStale: 'Refresh the review queue before deciding.',
      mapReadFailed: 'Read failed',
      failDetails: 'Details',
      recoveryReadFailed: 'could not read interrupted approvals',
      engineBannerUnverified: 'Engine not taken over yet',
      engineBannerRecovery: 'Engine installation interrupted',
      engineBannerMissing: 'Engine not installed',
      engineBannerUpdate: 'Engine update ready',
      engineShips: selected => `This plugin ships engine ${selected}. Preview update shows the plan before anything changes.`,
      root: 'Project root',
      pick: 'Choose folder…',
      pickAgain: 'Pick another file…',
      pickTitle: 'Pick a file inside the wiki folder',
      pickFilter: 'Wiki project (.json, .md)',
      pickAny: 'All files',
      scanRootPick: 'Choose scan folder…',
      scanRootSaved: p => `scan root saved: ${p}`,
      scanScanned: n => plural(n, '1 folder scanned', `${n} folders scanned`),
      scanSkipped: n => plural(n, '1 folder unreadable', `${n} folders unreadable`),
      scanTruncated: 'scan stopped early (too many folders)',
      sameId: 'SAME ID',
      sameIdHint: 'This path is a copy or a mirror: it carries the project id of the current root.',
      forceAsk: 'This path has the same project id as the current root — it looks like a copy or a mirror. Using it as the root weakens the backup check. Use it anyway?',
      forceYes: 'Yes, take it',
      forceNo: 'Cancel',
      noPicker: 'no file picker in this environment — type the path instead',
      pickCancelled: 'selection cancelled',
      derived: root => `root found: ${root}`,
      verify: 'Verify',
      verified: (pages, id) => `Verified · ${plural(pages, '1 page', `${pages} pages`)} · id ${id}`,
      save: 'Save',
      saved: root => `saved: ${root} — the automation now watches this root`,
      scan: 'Scan for candidates',
      candidates: 'Wiki projects found',
      candPages: n => plural(n, '1 page', `${n} pages`),
      scriptsMissing: 'missing',
      scriptsAll: 'nothing missing',
      filterPlaceholder: 'Filter candidates',
      filterNone: 'no candidate matches the filter',
      filterNoneHint: 'clear the field to see the whole candidate list',
      candidateHint: 'Clicking puts this root in the draft',
      noCandidates: root => `no other wiki project under ${root}`,
      invalid: 'Not verified',
      ok: 'Verified',
      loud: 'Without a wiki folder the jobs do not stay silent; they raise an alert.',
      placeholder: 'full path to the wiki folder',
      working: 'working…',
      loadFailed: 'could not read the automation state',
      staleNote: 'the last refresh failed — showing the previous reading',
      jobsReadFailed: 'could not read the scheduled jobs',
      ofTotal: (n, total) => `${n} of ${total}`,
      durSecs: secs => `${secs} s`,
      toneOk: 'OK',
      toneWarn: 'Needs attention',
      toneBad: 'Failed',
      toneQuiet: 'Nothing to report',
      unavailable: 'automation package not found on this machine (~/.llmwiki-audit)',
      install: 'Engine and files',
      engineMissing: 'Engine not installed',
      engineExistingUnverified: 'Existing engine found — not yet verified by this panel. Preview an update to see whether it can be adopted; nothing changes until you confirm the plan.',
      engineJobAdopt: 'adopted in place: schedule and on/off state kept; working folder, interpreter and launcher updated',
      engineJobAdoptPaused: 'adopted in place and paused: new drafting prompt and tools; turn it on in Tasks after checking',
      engineJobKeep: 'kept as is',
      engineJobRefreshPrompt: 'kept with its schedule and on/off state; drafting instructions updated to this release',
      engineJobRefreshInterpreter: 'kept with its schedule and on/off state; now runs with the Python Hermes uses',
      engineJobNew: 'new, paused',
      engineChoose: 'Choose project folder…',
      enginePickTitle: 'Pick a file directly inside the project folder',
      enginePickHint: 'The picker selects a file. Its containing folder becomes the project root; select a file directly inside your project, not inside a subfolder.',
      enginePreview: 'Preview install',
      engineUpdate: 'Preview update',
      engineApplying: 'Installation in progress — wait before retrying.',
      engineRecovery: 'Recovery required — review the original approved installation before resuming. No automatic rollback is available.',
      engineRecoveryReview: 'Review interrupted installation',
      engineRecoveryResume: 'Resume this exact installation',
      engineRecoveryOriginal: 'Original approved installation',
      engineRecoveryLabel: 'Original approved installation review',
      engineRecoveryRevision: 'Original approved revision',
      engineRecoveryRequestedRoot: 'Original requested root',
      engineRecoveryInstallId: 'Original install id',
      engineRecoveryPlanDigest: 'Original plan digest',
      engineRecoveryFresh: 'This is fresh approval in this app session, not a transfer of previous-session approval.',
      engineRecoveryAdmin: 'The service must verify the same administrator in this fresh app session. Pending, legacy or foreign-owner installations cannot be adopted.',
      engineRecoveryExpiry: 'Review expires at',
      engineRecoveryExpired: 'This recovery review expired. Review the interrupted installation again.',
      engineUnavailable: 'Engine installation is unavailable.',
      engineIdentityUnavailable: 'App connection or profile identity is unavailable.',
      enginePrepared: 'A prepared plan exists. Preview it before confirming.',
      engineRevision: 'Selected revision',
      engineProjectId: 'Project id',
      engineCodeDir: 'Engine code folder',
      engineDataDir: 'Engine data folder',
      engineInstallId: 'Prepared install id',
      enginePlanDigest: 'Plan digest',
      engineConfirm: 'Install this exact plan',
      engineConsequence: 'Installing does not publish sources or activate new jobs.',
      engineInstalled: 'Installed — activation required',
      engineActivate: 'Resume jobs separately in Scheduled jobs.',
      engineApplyFailed: 'Engine installation was not confirmed.',
      enginePrepareFailed: 'Could not prepare the engine plan.',
      engineStatusFailed: 'Could not read the engine installation state.',
      engineScopeChanged: 'Project or app context changed. Preview again before confirming.',
      enginePlanInvalid: 'The prepared plan is incomplete or does not match this preview.',
      enginePlanLabel: 'Prepared installation plan',
      engineAbsolute: 'Choose a file using an absolute project path.',
      engineRootLabel: 'Project root for engine install',
      engineDiscard: 'Discard plan',
      engineRetryStatus: 'Retry status',
      engineExisting: 'Installed — existing jobs unchanged',
      engineExistingNote: 'Existing job activation is unchanged. The new engine is not proven until its jobs run; check their next runs in History. Manage jobs separately in Scheduled jobs.',
      settingsFile: 'Settings file',
      auditDir: 'Automation folder',
      scripts: 'Scripts',
      jobsSection: 'Scheduled jobs',
      rootSection: 'Wiki folder',
      jobsLive: (live, paused, total) => paused ? `${live} of ${total} jobs live · ${paused} paused`
        : `${live} of ${total} jobs live`,
      jobNoId: 'No job ID',
      jobAttention: 'Needs attention',
      jobAgent: 'Agent',
      jobAgentNote: 'created by the engine installer (python install.py)',
      jobId: 'id',
      jobNoSchedule: 'no schedule in the config',
      jobLiveState: 'Live',
      jobPausedState: 'Paused',
      jobCreate: 'Create in installation',
      jobPause: 'Pause job',
      jobResume: 'Resume job',
      jobDelete: 'Delete job',
      jobAsk: 'Delete this scheduler entry? The panel keeps the definition and can create it again.',
      jobConfirm: 'Delete',
      jobCancel: 'Cancel',
      jobRootMissing: 'the wiki root is not verified — the script would alert on every run',
      jobScriptMissing: name => `the script ${name} is missing from the automation folder`,
      jobReadOnly: 'This Hermes version does not offer the cron store lock, so job changes stay off.',
      jobNoStore: 'the app cron store is not reachable from this backend, so jobs cannot be managed here',
      jobOrphans: n => plural(n,
        'one live job has no working target — pause it, or point it at a folder',
        `${n} live jobs have no working target — pause them, or point them at folders`),
      jobDonePause: 'job paused',
      jobDoneResume: 'job resumed',
      jobDoneRemove: 'job deleted',
      jobFailed: 'the action failed',
      jobSchedule: 'Schedule',
      jobScheduleSave: 'Save schedule',
      jobScheduleHint: 'Hermes runs this job on the schedule it has saved. Saving here replaces that schedule.',
      jobScheduleDone: (human, expr) => `schedule saved: ${human} (${expr})`,
      schFreq: 'Frequency',
      modeMinutes: 'Minutes',
      modeHourly: 'Hourly',
      modeDaily: 'Daily',
      modeWeekly: 'Weekly',
      modeMonthly: 'Monthly',
      modeCustom: 'Custom',
      schEvery: 'Every',
      schMinUnit: n => `${n} min`,
      schAtMinute: 'At minute',
      schAt: 'At',
      schOnDays: 'On',
      schOnDay: 'On day',
      schCron: 'Cron expression',
      schNoDay: 'pick at least one day',
      schShortMonth: 'months without this day are skipped',
      schCustomNote: 'five fields: minute · hour · day of month · month · day of week',
      schKeptNote: 'this schedule has no visual form here, so it opens as written and is kept unless you change it',
      schZone: (name, offset) => `Times are in the store's time zone: ${name ? `${name} ` : ''}(UTC${offset})`,
      schPreview: 'Preview',
      schNextRuns: 'Next runs',
      schChecking: 'checking…',
      schPreviewRefused: 'the store would refuse this schedule',
      schEveryMin: n => `Every ${n} minutes`,
      schHourTop: 'Every hour, on the hour',
      schHourAt: mm => `Every hour at :${mm}`,
      schDaily: time => `Every day at ${time}`,
      schWeekdays: time => `Weekdays at ${time}`,
      schWeekends: time => `Weekends at ${time}`,
      schWeekly: (names, time) => `${names.length < 2 ? names.join('')
        : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`} at ${time}`,
      schMonthly: (day, time) => `Day ${day} of every month at ${time}`,
      schCustom: 'Custom schedule',
      schCronTip: 'the cron expression the store holds',
      dayShort: 'Mon Tue Wed Thu Fri Sat Sun',
      dayPlural: 'Mondays Tuesdays Wednesdays Thursdays Fridays Saturdays Sundays',
      dayToday: time => `today ${time}`,
      dayTomorrow: time => `tomorrow ${time}`,
      dayYesterday: time => `yesterday ${time}`,
      dayOther: (day, dd, mm, time) => `${day} ${dd}.${mm} ${time}`,
      relNow: 'now',
      relIn: (n, unit) => `in ${n} ${unit}`,
      relAgo: (n, unit) => `${n} ${unit} ago`,
      span: (n, unit) => `${n} ${unit}`,
      unitMin: 'min',
      unitHour: 'h',
      unitDay: 'd',
      runNext: 'Next',
      runLast: 'Last',
      runNever: 'not run yet',
      runPaused: 'none while paused',
      runOk: 'OK',
      runFailed: 'Failed',
      runDeliveryFailed: 'Delivery failed',
      runLate: 'Late',
      runMissed: 'Missed',
      runLateTip: (due, started, late) => `due ${due}, started ${started} — ${late} late`,
      runMissedTip: (due, started, late) => `missed its slot: due ${due}, caught up at ${started} (${late} late)`,
      jobDeleteHint: 'the entry leaves the scheduler; the runs it already made stay in the log.',
      jobDriftStore: 'the store holds ',
      jobDriftConfig: ' while the config still asks for ',
      candNone: 'no candidate waiting',
      candNoneHint: 'the nightly session harvest drafts new ones here',
      candReadFailed: 'could not read the candidates',
      candShowFailed: 'could not read this candidate',
      candNew: 'New page',
      candUpdate: 'Update',
      candCorrection: 'Correction',
      candCorrects: name => `Corrects the version you approved earlier (${name}). The text below shows what changes.`,
      candSuperseded: name => `A newer draft of this source is waiting (${name}). Approve that one and reject this one.`,
      candBlocked: 'This draft cannot be applied:',
      candStaleDraft: 'The page changed after this draft was written.',
      candRederived: name => `Rewritten onto the page as it is now, from an older draft (${name}). Only the text the older draft changed is changed; approve this version.`,
      candRetire: 'Retire',
      candDiff: 'Diff against the current source',
      candNoDiff: 'no change to show',
      candFormat: 'Format',
      candFormatOk: 'Passes the house format',
      candEvidence: 'Evidence',
      candEvidenceNone: 'no evidence folder',
      candRequests: 'Evidence to fetch',
      candRequestsHint: 'These facts need a stored copy of their source before they can enter the wiki. Nothing has been downloaded yet. Check each address and quoted passage, then fetch: a copy is kept only when every passage is in the downloaded file.',
      candRequestSource: 'Source',
      candRequestSupports: 'Backs',
      candRequestPassages: 'Must contain',
      candRequestFetched: 'fetched',
      candRequestWaiting: 'not fetched',
      candRequestFailed: 'not fetched:',
      candFetch: n => `Fetch evidence (${n})`,
      candFetching: 'Fetching…',
      candFetchDone: 'Evidence fetched and checked. Review the stored copies, then approve.',
      candRefusal: 'This draft cannot be approved as written.',
      candRefusalHint: 'Approval runs the same check, so the wiki cannot take the draft in this form. Reject it with this reason.',
      candTarget: 'Target',
      candTargetExists: 'replaces the current file',
      candTargetNew: 'a new file',
      candWhy: 'Why',
      candApprove: 'Approve',
      candApproveAsk: 'Approve this candidate?',
      candApproveYes: 'Approve and write',
      candReject: 'Reject',
      candRejectSend: 'Reject candidate',
      candRejectReason: 'Why is it rejected?',
      candApproved: 'candidate approved — the source is in the wiki',
      recoveryTitle: 'Interrupted approvals',
      recoveryResume: 'Resume',
      recoveryDone: 'Approved operation completed.',
      setupOffTitle: 'Owner approval is off',
      setupOff: 'You can read and reject candidates, but none can be approved and no new candidates are drafted until owner approval is on.',
      setupChanged: 'Wiki Automation was updated. Turn owner approval on again so it trusts the new code.',
      setupOwner: owner => owner === 'local_owner'
        ? 'Approvals are bound to this computer\'s Hermes session in this profile.'
        : `Approvals are bound to the signed-in account ${owner} in this profile.`,
      setupJob: (name, schedule) => `${name || 'Session Harvest'}${schedule ? ` (${schedule})` : ''} drafts `
        + 'candidates with the wiki drafting tools only; it cannot approve or write to the wiki.',
      setupRestart: 'A background runtime check is turned on; the background service needs one restart afterwards, started from here.',
      setupTurnOn: 'Turn on owner approval',
      setupConfirm: 'Confirm and turn on',
      setupDone: 'Owner approval is on. Restart the background service to finish.',
      setupPendingTitle: 'Restart the background service to finish',
      setupPending: 'Owner approval is on, but the background service that runs scheduled tasks has not loaded it yet. Approvals stay off until it restarts. Restarting the app alone does not restart it.',
      setupRestartWhat: 'Scheduled tasks pause for about half a minute. A task running right now is stopped.',
      setupRestartArm: 'Restart background service',
      setupRestartConfirm: 'Restart now',
      setupRestarting: 'Restarting the background service…',
      setupRestartReady: 'Owner approval is ready.',
      setupRestartLate: 'The background service was restarted, but owner approval is still not ready after two minutes. Try once more; if it stays, open Details in Watch Dog.',
      setupReadFailed: 'could not read the owner approval setup',
      candRejected: 'candidate rejected',
      candFailed: 'the candidate action failed',
      candOwnerUnavailable: 'The engine did not return an exact, pending owner decision. Refresh and review again.',
      refresh: 'Refresh',
      checkAsWritten: 'As written',
      checkUnrecognized: 'Unrecognized check output',
      helpRefused: 'Why this was refused',
      helpNote: 'Note',
      helpResult: 'Result',
      reasonDeriveNoIdentity: 'no .llm-wiki/project.json above the picked path — pick a file INSIDE the wiki folder',
      reasonFolderMissing: 'top-level folder not found',
      reasonIdentityMissing: 'no .llm-wiki/project.json — this folder is not a wiki root',
      reasonIdentityUnreadable: '.llm-wiki/project.json could not be read',
      reasonPathRequired: 'a path is required',
      reasonRootMissing: 'project root not found: ',
      reasonRootNotChosen: 'project root not chosen',
      reasonScanRootMissing: 'scan root not found: ',
      reasonScanRootUnknown: 'scan root unknown — pick a folder',
      reasonWikiEmpty: 'wiki/ is empty or the project id is missing',
      reasonWikiMissing: 'no wiki/ folder'
    },
    wd: {
      journalTitle: 'Run journal',
      journalFilters: 'Job & date filters',
      journalFiltersActive: 'Filters active',
      runDetail: 'Run detail',
      claimedAt: 'Claimed',
      notification: 'Notification',
      reportedError: 'Reported error',
      reportedFinding: 'Reported finding',
      noReportedError: 'No error reported.',
      errorNotRecorded: 'No separate error text is recorded.',
      durationSnapshot: 'Duration across this snapshot',
      durationSnapshotHint: 'Each bar is a recorded run, not a forecast.',
      durationNone: 'No recorded duration can be placed in this snapshot.',
      technicalDetails: 'Technical details',
      runMetadata: 'Run metadata',
      historicalJob: 'Historical job',
      traceNote: 'Time is the recorded claim time. Run metadata is available today; '
        + 'stage-by-stage traces require engine support.',
      journalPick: 'Select a run',
      journalPickHint: 'Open a record to read its output, findings and metadata.',
      statusFilter: 'Run status filter',
      completed: 'Completed',
      active: 'Active',
      refresh: 'Refresh',
      readAt: at => `Read at ${at}`,
      win24h: 'last 24 hours',
      win7d: 'last 7 days',
      win30d: 'last 30 days',
      winAll: 'all history',
      staleNotice: why => `The run log could not be refreshed; showing the last good read. ${why}`,
      bodyFail: why => `The full body could not be loaded; the preview is shown. ${why}`,
      window: (label, n) => `Window: ${label} · ${n} runs`,
      truncated: n => `The list is capped at ${n} runs (older history is not loaded).`,
      rows: n => wdPlural(n, 'run', 'runs'),
      filterHits: (hits, total) => `${hits} of ${wdPlural(total, 'run', 'runs')} shown`,
      filterPlaceholder: 'Filter runs — job, output or status…',
      filterClear: 'Clear filters',
      all: 'All',
      allJobs: 'All jobs',
      jobsSelect: 'Job filter',
      jobsN: n => wdPlural(n, 'job', 'jobs'),
      sortSelect: 'Sort',
      sortNew: 'Newest first',
      sortOld: 'Oldest first',
      sortJob: 'By job',
      sortStatus: 'By status',
      today: 'Today',
      days7: 'Last 7 days',
      days30: 'Last 30 days',
      startFace: 'Start',
      endFace: 'End',
      startDate: 'Start date',
      endDate: 'End date',
      dateClear: 'Clear date',
      dateNotSet: 'not set',
      calPrev: 'Previous month',
      calNext: 'Next month',
      weekdays: 'Mo Tu We Th Fr Sa Su',
      undated: 'no date',
      chartFlow: 'Run flow',
      chartFlowMeta: days => `last ${days} days`,
      chartFlowSum: (total, all, day) => `${wdPlural(total, 'run', 'runs')}`
        + (all > total ? ` of ${all}` : '') + (day ? ` · peak ${day}` : ''),
      clear: 'Archive & clear',
      clearAsk: (total, n, kept) => (kept
        ? `Of ${wdPlural(total, 'shown run', 'shown runs')}, ${n} will be written to backups/ and removed from `
          + `the run store; ${wdPlural(kept, 'running run is', 'running runs are')} kept, because the `
          + 'scheduler still owns it.'
        : `${wdPlural(n, 'record', 'records')} will be written to backups/ and removed from the run store.`)
        + ' Nothing is removed until the archive is written and read back.',
      clearLabel: 'Archive and clear the shown runs',
      clearGo: 'Archive & clear',
      clearCancel: 'Cancel',
      clearBusy: 'Archiving…',
      cleared: (n, missing, file) => `${wdPlural(n, 'record', 'records')} archived to ${file} and removed`
        + (missing ? ` · ${wdPlural(missing, 'record', 'records')} already gone` : ''),
      clearNone: 'No record matched, so nothing was archived or removed.',
      clearNoAnswer: 'the run store did not answer',
      clearFail: why => `Nothing was removed: ${why}`,
      ckBad: 'failed',
      ckWarn: 'silent',
      ckNeutral: 'ok',
      deltaTip: (basis, before) => `${before} in the previous ${basis}`,
      deltaNone: 'no previous window to compare with',
      deltaApprox: (basis, before) => `approximate: at least ${before} in the previous ${basis}, the store holds more runs than one read covers`,
      frTitle: 'Freshness',
      frMeta: jobs => wdPlural(jobs, 'job', 'jobs'),
      frSince: 'since the last run',
      unitShort: (n, unit) => `${n} ${unit}`,
      unitMin: 'min',
      unitHour: 'h',
      unitSec: 's',
      frOverdue: mins => `the next run is overdue by ${mins} min`,
      frClean: mins => (mins > 0 ? `next run in ${mins} min` : 'the next run is due now'),
      frNoRing: 'no cycle',
      frSummary: (failed, silent, delivered) => (failed || silent
        ? `${failed} failed · ${silent} silent · ${delivered} delivered`
        : `${wdPlural(delivered, 'run', 'runs')} delivered, nothing failed`),
      frNoCycle: 'no next run reported — nothing to measure',
      frPick: 'filter the log to this job',
      frNone: 'no job reports a cycle right now',
      secs: n => `${n} s ago`,
      mins: n => `${n} min ago`,
      actTitle: 'Activity by job',
      actMeta: (span, narrowed) => `last ${span >= 48 ? wdPlural(Math.round(span / 24), 'day', 'days') : `${span} h`}`
        + (narrowed ? ' · all runs' : ''),
      actNone: 'no run to place in this window',
      actCell: (iso, runs) => `${iso} · ${wdPlural(runs, 'run', 'runs')}`,
      actMore: n => `+${wdPlural(n, 'job', 'jobs')} in this window`,

      noBody: 'no body record',
      noBodyAnswer: 'the answer carried no body',
      copyFail: why => `The output could not be copied: ${why}`,
      loading: 'loading the body…',
      loadingRuns: 'Reading the run log…',
      close: 'Close',
      copy: 'Copy',
      copied: 'Copied',
      when: 'Run time',
      job: 'Job',
      status: 'Status',
      delivery: 'Delivery',
      duration: 'Duration',
      lateness: 'Lateness',
      bodysrc: 'Body source',
      deletedJob: 'deleted job',
      deletedNote: 'This job is no longer defined; its run history is kept as the record.',
      sec: n => `${n} s`,
      ms: n => `${n} ms`,
      min: n => `${n} min`,
      readError: 'The cron run log could not be read',
      readErrorTitle: 'Run log unreadable',
      emptyTitle: 'No runs recorded',
      emptyBody: 'No cron run falls in the selected window. An empty list means no job fired — check '
        + 'that the Hermes scheduler runs and jobs exist.',
      emptyRangeTitle: 'No runs in this range',
      emptyRangeBody: 'No run falls in the chosen date range. Press "All" to see everything.',
      emptyMatchTitle: 'No matching runs',
      emptyMatchBody: q => `Nothing matches "${q}". Clear the filter to see all runs.`,
      emptyPickBody: 'No run of this kind in the shown window. Pick "All" or another job to see more.',
      kpi: {
        runs: 'Runs',
        runsHint: n => `${wdPlural(n, 'row', 'rows')} in scope`,
        failed: 'Failed',
        failedHint: 'status: failed',
        silent: 'Silent',
        silentHint: 'no output to deliver',
        delivered: 'Delivered',
        deliveredHint: 'reached its target',
        withFindings: 'Findings',
        withFindingsHint: 'output has findings'
      },
      badge: {
        done: 'Done',
        failed: 'Failed',
        running: 'Running',
        starting: 'Starting',
        unknown: 'Unknown',
        delivered: 'Delivered',
        silent: 'Silent',
        queued: 'Queued',
        delivFailed: 'Delivery failed',
        none: 'No record'
      },
      asWritten: 'As written',
      map: {
        notIndexed: d => `Retired check: ${d.n ?? '?'} ${Number(d.n) === 1 ? 'page was' : 'pages were'} reported outside index.md. The engine no longer runs this check, since LLM Wiki v0.6.12 keeps index.md as a bounded list of the 200 most recently updated pages.`,
        wikilink: d => `${d.n ?? '?'} ${Number(d.n) === 1 ? 'link is' : 'links are'} written as a path ([[a/b]]), so the app graph draws no edge — write it as [[page-name]].`,
        dup: () => 'Two pages share one name — the [[link]] target is ambiguous and the app graph draws no edge.',
        drift: () => 'The Hermes, Codex and Claude setups differ — sync the difference or record it as intentional.',
        mirror: d => `${d.n ?? '?'} commits never reached the '${d.remote ?? '?'}' mirror — run the backup.`,
        identity: d => `The app's ACTIVE project id changed: ${d.id ?? '?'} (expected ${d.expected ?? '?'}).`,
        unresolvable: () => 'A body link points at a page that does not exist — create the target page or fix the link.',
        isolated: d => `${d.n ?? '?'} ${Number(d.n) === 1 ? 'page has' : 'pages have'} no links at all (graph degree ≤ 1), so nothing in the app graph points to ${Number(d.n) === 1 ? 'it' : 'them'}.`,
        pagesDown: d => `Page count dropped: ${d.before ?? '?'} → ${d.after ?? '?'}.`,
        crash: d => `The ${d.fn ?? '?'} checker crashed: ${d.error ?? '?'}.`,
        evidenceStore: d => `${d.n ?? '?'} ${Number(d.n) === 1 ? 'problem' : 'problems'} in the evidence store — run evidence_capture.py --verify in the engine folder.`,
        evidenceStale: d => `${d.n ?? '?'} evidence ${Number(d.n) === 1 ? 'passage no longer matches' : 'passages no longer match'} the installed LLM Wiki or Hermes version — run evidence_capture.py --recheck.`,
        controlMissing: d => `${d.name ?? 'A control file'} is missing from the wiki folder — restore it from git.`,
        controlChanged: d => `${d.name ?? 'A control file'} differs from its version in git — the app may have rewritten it; compare the two.`,
        controlTemplate: d => `${d.name ?? 'A control file'} has the size of the app's blank template — the Create Project flow may have written over the project.`,
        projectFileMissing: () => '.llm-wiki/project.json is missing — the app will start the project over with a new id; restore the file from git.',
        projectFileUnreadable: () => '.llm-wiki/project.json cannot be read — the file is damaged; restore it from git.',
        projectReregistered: d => `The app registered this folder again: id ${d.id ?? '?'} (expected ${d.expected ?? '?'}) — check the content, then restore .llm-wiki/project.json from git.`,
        indexStale: d => `${d.n ?? '?'} ${Number(d.n) === 1 ? 'page is' : 'pages are'} listed in index.md but ${Number(d.n) === 1 ? 'has' : 'have'} no file — the page may have been renamed.`,
        unsplitIngest: d => `${d.n ?? '?'} ${Number(d.n) === 1 ? 'page holds' : 'pages hold'} an unsplit ingest output — the pages in its ---FILE: blocks were never written; ingest that source again.`,
        mcpOff: () => '"Enable MCP access" is off in the app — MCP tools refuse although clients show Connected; turn it on in Settings → API + MCP.',
        commitBacklog: d => `${d.n ?? '?'} wiki ${Number(d.n) === 1 ? 'change has' : 'changes have'} not been committed for ${d.hours ?? '?'} hours — the automatic commit is not saving.`,
        driftCrash: () => 'The agent-setup check crashed — a checker bug; it says nothing about the setups.',
        harvestUnread: d => `The harvest does not read ${d.n ?? '?'} Codex ${Number(d.n) === 1 ? 'session' : 'sessions'} — their file type is not in its list.`,
        harvestZstd: d => `${d.n ?? '?'} compressed Codex ${Number(d.n) === 1 ? 'session' : 'sessions'} cannot be read: this Python has no zstd decoder (3.14 or later is needed).`,
        engineCopies: d => `${d.n ?? '?'} engine ${Number(d.n) === 1 ? 'script' : 'scripts'} in the data folder ${Number(d.n) === 1 ? 'differs' : 'differ'} from the installed version — an old copy can bypass the approval gates.`,
        other: () => 'Unrecognized finding — no pattern matched; the checker line is shown as written.'
      },
      field: {
        body: 'Run output',
        findings: 'Findings'
      }
    }
  }
}

function registerTitle() {
  const viaApp = ctxRef?.i18n?.t?.('wa.title')
  return viaApp && viaApp !== 'wa.title' ? viaApp : BUNDLES.en.wa.title
}

const api = {
  automation: () => ctxRef.rest('/automation'),
  runs: (limit) => ctxRef.rest(`/runs?limit=${encodeURIComponent(limit)}`),
  validate: path => ctxRef.rest('/automation/validate', { method: 'POST', body: { path } }),
  derive: picked => ctxRef.rest('/automation/derive', { method: 'POST', body: { picked } }),
  candidates: root => ctxRef.rest(`/automation/candidates${root ? `?root=${encodeURIComponent(root)}` : ''}`),
  scanRoot: path => ctxRef.rest('/automation/scan_root', { method: 'POST', body: { path } }),
  save: (project_root, force) => ctxRef.rest('/automation/settings',
    { method: 'POST', body: { project_root, force: Boolean(force) } }),
  jobs: () => ctxRef.rest('/jobs'),
  wikiMap: async () => {
    const res = await ctxRef.rest('/wiki/map')
    if (!res || res.ok !== true) throw new Error(res?.error || BUNDLES.en.wa.globeUnread)
    return res
  },
  engineStatus: () => ctxRef.rest('/engine/status'),
  harvestStatus: async () => {
    const res = await ctxRef.rest('/harvest/status')
    if (!res?.ok) throw new Error(res?.error || BUNDLES.en.wa.mapReadFailed)
    return res
  },
  candList: () => ctxRef.rest('/candidates'),
  recoverable: () => ctxRef.rest('/owner/recoverable'),
  recover: request_id => ctxRef.rest('/owner/recover', { method: 'POST', body: { request_id } }),
  ownerSetup: () => ctxRef.rest('/owner/activation'),
  ownerActivate: plan_digest => ctxRef.rest('/owner/activation', { method: 'POST', body: { confirm: true, plan_digest } }),
  candShow: ref => ctxRef.rest(`/candidates/show?ref=${encodeURIComponent(ref)}`),
  candFetch: (ref, review_digest) => ctxRef.rest('/candidates/act',
    { method: 'POST', body: { ref, action: 'fetch_evidence', review_digest } }),
  candAct: (ref, action, confirm, reason, review_digest, request_id) => ctxRef.rest(
    action === 'approve' ? '/owner/decision' : '/candidates/act',
    { method: 'POST', body: action === 'approve'
      ? { ref, review_digest, confirm: Boolean(confirm), ...(confirm ? { request_id } : {}) }
      : { ref, action, confirm: Boolean(confirm), reason,
        ...(review_digest ? { review_digest } : { unreviewable: true }) } }),
  jobAct: (row, action, confirm, schedule) => ctxRef.rest('/jobs/act',
    { method: 'POST', body: { role: row.role, action, confirm: Boolean(confirm), schedule,
      expected: { id: String(row.id || ''), state: String(row.state || ''), schedule: String(row.schedule || '') } } }),
  jobPreview: schedule => ctxRef.rest('/jobs/preview', { method: 'POST', body: { schedule } })
}

const healthApi = {
  jobs: async win => {
    const res = await ctxRef.rest(`/health/jobs?window=${encodeURIComponent(win)}`)
    if (res && res.ok === false) throw new Error(res.error || BUNDLES.en.wd.readError)
    return res
  },
  watchdog: async () => {
    const res = await ctxRef.rest('/health/watchdog')
    if (res && res.ok === false) throw new Error(res.error || BUNDLES.en.wd.readError)
    return res
  },
  jobRun: id => ctxRef.rest(`/health/jobs/run?id=${encodeURIComponent(id)}`),
  archiveClear: keys => ctxRef.rest('/health/runs/archive-clear', { method: 'POST', body: { keys } })
}

function usePolling(fn, ms, deps) {
  const [state, setState] = useState({ data: null, error: null, busy: false })
  const alive = useRef(true)
  const inFlight = useRef(0)
  const generation = useRef(0)
  const latestFn = useRef(fn)
  latestFn.current = fn

  const load = async tick => {
    if (tick === true && inFlight.current) return
    const ticket = ++generation.current
    inFlight.current += 1
    setState(prev => ({ ...prev, busy: true }))
    try {
      const data = await latestFn.current()
      if (alive.current && ticket === generation.current) setState({ data, error: null, busy: false })
    } catch (e) {
      if (alive.current && ticket === generation.current) {
        setState(prev => ({ ...prev, error: errText(e), busy: false }))
      }
    } finally {
      inFlight.current -= 1
    }
  }

  useEffect(() => {
    alive.current = true
    load()
    const id = ms > 0 ? setInterval(() => { if (!document.hidden) load(true) }, ms) : null
    return () => { alive.current = false; if (id !== null) clearInterval(id) }
  }, [ms, ...(deps || [])])

  return { ...state, refresh: load }
}

const sdkScope = () => JSON.stringify([host.state.connectionId.get(), host.state.profile.get(),
  host.state.cwd?.get()])
const panelProject = data => JSON.stringify([data?.settings?.project_root || '', data?.settings?.project?.id || ''])

function usePanelPolling(fn, ms) {
  const [state, setState] = useState({ data: null, error: null, busy: true, scope: null })
  const alive = useRef(true)
  const epoch = useRef(0)
  const project = useRef(null)
  const pending = useRef(null)
  const again = useRef(false)
  const capture = () => ({ sdk: sdkScope(), epoch: epoch.current })
  const matches = token => alive.current && token.sdk === sdkScope() && token.epoch === epoch.current
  const invalidate = () => {
    epoch.current += 1
    project.current = null
    pending.current = null
    setState({ data: null, error: null, busy: true, scope: null })
  }
  const load = async tick => {
    if (!alive.current) return
    if (pending.current) {
      if (tick !== true) again.current = true
      return
    }
    let token = capture()
    const ticket = {}
    pending.current = ticket
    setState(previous => ({ ...previous, busy: true }))
    try {
      if (!matches(token)) return
      let context = null
      try { context = await api.automation() }
      catch (error) { if (fn === api.automation) throw error }
      if (!matches(token)) return
      if (fn === api.automation && !context) throw new Error(BUNDLES.en.wa.loadFailed)
      const key = panelProject(context)
      if (project.current !== null && project.current !== key) epoch.current += 1
      project.current = key
      token = capture()
      const data = fn === api.automation ? context : await fn()
      if (!matches(token)) return
      const scope = context?.settings && context.available !== false
        ? { key: JSON.stringify([token.sdk, token.epoch, key]), project: key,
          matches: () => matches(token), fresh: () => matches(token) && pending.current === null }
        : null
      setState({ data, error: null, busy: false, scope })
    } catch (error) {
      if (matches(token)) {
        epoch.current += 1
        setState(previous => ({ ...previous, error: errText(error), busy: false, scope: null }))
      }
    } finally {
      if (pending.current === ticket) {
        pending.current = null
        if (again.current && alive.current) { again.current = false; void load() }
      }
    }
  }
  useEffect(() => {
    alive.current = true
    const switched = () => { invalidate(); void load() }
    const stops = [host.state.connectionId.listen(switched), host.state.profile.listen(switched),
      host.state.cwd?.listen(switched)].filter(Boolean)
    void load()
    const timer = setInterval(() => { if (!document.hidden) void load(true) }, ms)
    return () => { alive.current = false; epoch.current += 1; stops.forEach(stop => stop()); clearInterval(timer) }
  }, [])
  const token = capture()
  return { ...state, refresh: () => { if (matches(token)) void load() } }
}

function usePanelActions(scopes, reset) {
  const key = JSON.stringify(scopes.map(scope => scope?.key || null))
  const frame = useRef(key)
  frame.current = key
  const seen = useRef(key)
  const alive = useRef(true)
  const pending = useRef(null)
  const matches = () => alive.current && frame.current === key && scopes.every(scope => scope?.matches())
  useLayoutEffect(() => {
    if (seen.current !== key) { seen.current = key; pending.current = null; reset() }
  }, [key])
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; pending.current = null }
  }, [])
  const begin = () => {
    if (!matches() || !scopes.every(scope => scope?.fresh()) || pending.current) return null
    const ticket = {}
    pending.current = ticket
    return ticket
  }
  const current = ticket => matches() && pending.current === ticket
  const finish = ticket => {
    if (!current(ticket)) return false
    pending.current = null
    return true
  }
  return { matches, begin, current, finish, cancel: () => { pending.current = null } }
}

function useFolioPolling() {
  const [state, setState] = useState({ candidates: null, recovery: null, error: null, busy: true, scope: null })
  const alive = useRef(true)
  const epoch = useRef(0)
  const project = useRef(null)
  const pending = useRef(null)
  const again = useRef(false)
  const capture = () => ({ sdk: sdkScope(), epoch: epoch.current, project: project.current })
  const matches = token => alive.current && token && token.sdk === sdkScope()
    && token.epoch === epoch.current && token.project === project.current
  const invalidate = () => {
    epoch.current += 1
    pending.current = null
    project.current = null
    setState({ candidates: null, recovery: null, error: null, busy: true, scope: null })
  }
  const load = async tick => {
    if (!alive.current) return
    if (pending.current) {
      if (tick !== true) again.current = true
      return
    }
    let token = capture()
    const ticket = {}
    pending.current = ticket
    setState(previous => ({ ...previous, busy: true }))
    try {
      if (!matches(token)) return
      const context = await api.automation()
      if (!matches(token)) return
      if (context?.available !== true || !context?.settings || typeof context.settings !== 'object'
        || !engineAbsolute(context.settings.project_root) || context.settings.project?.ok !== true
        || !engineText(context.settings.project.id)) throw new Error(BUNDLES.en.wa.candStale)
      const nextProject = JSON.stringify([context.settings.project_root || '', context.settings.project?.id || ''])
      if (project.current !== null && project.current !== nextProject) {
        invalidate()
        pending.current = ticket
      }
      project.current = nextProject
      token = capture()
      const scope = { key: token.epoch, matches: () => matches(token) && pending.current === null }
      if (!matches(token)) return
      const settled = promise => promise.then(data => ({ data, error: null }),
        error => ({ data: null, error: errText(error) }))
      const [candidates, setup] = await Promise.all([settled(api.candList()), settled(api.ownerSetup())])
      if (!matches(token)) return
      const recovery = setup.data?.ok === true && setup.data.active === true && setup.data.ready === true
        ? await settled(api.recoverable()) : null
      if (!matches(token)) return
      setState({ candidates, recovery, setup, error: null, busy: false, scope })
    } catch (error) {
      if (matches(token)) {
        invalidate()
        setState({ candidates: null, recovery: null, setup: null, error: errText(error), busy: false, scope: null })
      }
    } finally {
      if (pending.current === ticket) {
        pending.current = null
        if (again.current && alive.current) { again.current = false; void load() }
      }
    }
  }
  useEffect(() => {
    alive.current = true
    const switched = () => { invalidate(); void load() }
    const stops = [host.state.connectionId.listen(switched), host.state.profile.listen(switched),
      host.state.cwd?.listen(switched)].filter(Boolean)
    void load()
    const id = setInterval(() => { if (!document.hidden) void load(true) }, 60000)
    return () => { alive.current = false; epoch.current += 1; stops.forEach(stop => stop()); clearInterval(id) }
  }, [])
  const token = capture()
  const refresh = () => { if (matches(token)) void load() }
  return { ...state, refresh }
}

const FOLIO_H = { index: 520, indexNarrow: 192, diff: 220, facts: 420, dryRun: 180 }

function errText(error) {
  const bare = String(error?.message || error)
    .replace(/^Error invoking remote method \x27[^\x27]*\x27: (?:\w*Error: )?/, '')
  const coded = /^(\d{3}): (\{[\s\S]*\})\s*$/.exec(bare)
  if (coded) {
    try {
      const detail = JSON.parse(coded[2]).detail
      const said = Array.isArray(detail)
        ? detail.map(item => item?.msg).filter(msg => typeof msg === 'string' && msg).join('; ')
        : detail
      if (typeof said === 'string' && said) return `${said} (HTTP ${coded[1]})`
    } catch {
    }
  }
  return bare.trim()
}

const EASE = {
  standard: 'cubic-bezier(.4,0,.2,1)',
  entrance: 'cubic-bezier(0,0,.38,.9)',
  linear: 'linear',
  soft: 'ease'
}
const MOTION = {
  hover: { ms: 120, ease: EASE.standard },
  row: { ms: 200, ease: EASE.standard },
  caret: { ms: 200, ease: EASE.standard },
  drawer: { ms: 320, ease: EASE.entrance },
  spin: { ms: 900, ease: EASE.linear },
  march: { ms: 1100, ease: EASE.linear }
}
const move = (job, props) => String(props).split(',')
  .map(p => `${p.trim()} ${MOTION[job].ms}ms ${MOTION[job].ease}`).join(',')

const prefersReduced = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches
const instantMove = (job, props) => (prefersReduced() ? 'none' : move(job, props))

const SURFACE = '--hx-card:transparent;--hx-field:transparent;' +
  '--hx-raised:var(--ui-bg-elevated);--hx-panel:var(--ui-bg-elevated);--hx-line:var(--ui-stroke-tertiary)'

const STYLE = `
.wa-root{height:100%;min-height:0;overflow:auto;background:transparent;
  color:var(--ui-text-primary);padding:0;display:grid;gap:16px;align-content:start;
  grid-auto-rows:max-content;container-type:inline-size}
.wa-root{${SURFACE}}
.wa-card{border:1px solid var(--ui-stroke-tertiary);border-radius:var(--radius-xl,3.2px);
  background:var(--hx-card);overflow:hidden}
.wa-body{padding:14px;display:grid;gap:8px;min-width:0}
.wa-stale{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:baseline;margin:0 14px;padding:6px 10px;
  font-size:12px;color:var(--ui-text-primary);border-left:2px solid var(--ui-red);
  background:color-mix(in srgb,var(--ui-red) 7%,transparent)}
.wa-inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wa-path-input{flex:1 1 240px;min-width:160px}
.wa-loading{display:flex;align-items:center;justify-content:center;padding:16px 0}
.wa-empty{padding:4px 0}
.wa-clip{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.wa-grow{flex:1 1 auto}
.wa-mono{font-family:var(--dt-font-mono,monospace);font-size:12px;
  line-height:1.5}
.wa-kv{grid-template-columns:7.75rem minmax(0,1fr)}
.wa-engine{overflow-wrap:anywhere}
.wa-engine-plan{max-height:420px;overflow-y:auto;min-width:0;scrollbar-width:thin;
  scrollbar-color:var(--ui-text-tertiary) transparent}
.wa-engine-plan dd{white-space:pre-wrap;overflow-wrap:anywhere}
.wa-engine-plan:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.wa-bad{color:var(--ui-red)}
.wa-root .wa-danger{color:var(--ui-red)}
.wa-root .wa-badge{min-width:0;max-width:100%;white-space:normal;overflow-wrap:anywhere}
.wa-root .wa-danger-fill{background:var(--dt-destructive);color:var(--dt-destructive-foreground)}
.wa-root .wa-danger-fill:hover{background:color-mix(in srgb,var(--dt-destructive) 88%,transparent)}
.wa-root-value{display:flex;gap:8px;align-items:center;min-width:0}
.wa-icon-btn{border-radius:9999px}
.wa-msg{font-size:12px;padding:2px 12px}
.wa-msg::first-letter,.wa-hint::first-letter,.wa-fail-state [data-slot="error-state-description"]::first-letter,.wa-fail-state p::first-letter,.wa-help-title::first-letter{text-transform:uppercase}
.g-panel .wa-msg{padding:2px 0}
.wa-msg[data-tone="info"]{color:var(--ui-text-tertiary)}
.wa-msg[data-tone="bad"]{color:var(--ui-red)}
.wa-help .wa-msg{padding:0}
.wa-help{border:0;border-left:2px solid var(--ui-stroke-primary);border-radius:0;padding:10px 14px;
  display:grid;gap:4px;min-width:0;background:color-mix(in srgb,var(--ui-text-primary) 3%,transparent)}
.wa-help[data-tone="bad"],.wa-help:has(.wa-bad),.wa-help:has(.wa-msg[data-tone="bad"]){border-left-color:var(--ui-red);
  background:color-mix(in srgb,var(--ui-red) 6%,transparent)}
.wa-help[data-tone="ok"]{border-left-color:var(--ui-green)}
.wa-help .wa-bad,.wa-help .wa-msg[data-tone="bad"]{color:var(--ui-text-primary)}
.wa-help-title{font-size:12px;font-weight:600;color:var(--ui-text-primary)}
.wa-help-act{justify-self:end}
.wa-fail .wa-help{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;padding:8px 14px;
  border-left-color:var(--ui-red);background:color-mix(in srgb,var(--ui-red) 6%,transparent)}
.wa-desk .wa-body.wa-fail{padding:0}
.wa-fail .wa-help .wa-fail-dot{display:none}
.wa-fail .wa-fail-state{display:block;flex:1 1 auto;min-width:0}
.wa-fail .wa-fail-state>div{flex-direction:row;align-items:center;gap:8px;text-align:left}
.wa-fail .wa-fail-state p{margin:0;text-align:left;font-size:12px;line-height:18px;color:var(--ui-text-primary);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.wa-fail .wa-fail-state p.max-w-prose,.wa-fail .wa-fail-state p{max-width:none}
.wa-fail-dot{width:6px;height:6px;border-radius:50%;flex:0 0 auto;background:var(--ui-red)}
.wa-fail-more{flex:0 0 auto;font-size:12px;color:var(--ui-text-secondary)}
.wa-fail-more[open]{flex:1 1 100%}
.wa-fail-more summary{cursor:pointer;list-style:none}
.wa-fail-more summary::-webkit-details-marker{display:none}
.wa-fail-more summary:focus-visible{outline:1px solid var(--ui-accent);outline-offset:2px}
.wa-label{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ui-text-secondary)}
.wa-hint{font-size:12px;line-height:1.6;color:var(--ui-text-secondary);margin:0}
.wa-sec-title{font-size:12px;font-weight:600;color:var(--ui-text-secondary)}
.wa-raw{display:grid;gap:4px;min-width:0}
.wa-code-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.wa-jobs-note{grid-template-columns:auto minmax(0,1fr);align-items:baseline;gap:4px 8px;
  margin:0 12px 6px;padding:6px 10px;border:0;border-left:2px solid var(--ui-green);border-radius:0;
  background:color-mix(in srgb,var(--ui-green) 7%,transparent)}
.wa-jobs-note[data-tone="bad"]{border-left-color:var(--ui-red);
  background:color-mix(in srgb,var(--ui-red) 7%,transparent)}
.wa-jobs-note .wa-help-title{color:var(--ui-text-primary)}
.wa-jobs-note .wa-raw{grid-column:1 / -1}
.wa-jobs-sub{font-size:12px;color:var(--ui-text-secondary)}
.wa-job{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;
  padding:6px 12px;border-top:1px solid var(--ui-stroke-tertiary)}
.wa-job-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.wa-job-line{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0}
.wa-job-name{font-size:12px;color:var(--ui-text-primary)}
.wa-job-meta{font-size:12px;color:var(--ui-text-secondary)}
.wa-job-acts{display:grid;gap:6px;align-items:center;
  grid-template-columns:minmax(4.7rem,max-content) minmax(4.4rem,max-content) minmax(4.6rem,max-content);
  justify-content:end}
.wa-job-act{font-size:12px;justify-self:start;white-space:nowrap;height:28px;padding:0 10px;border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-lg,2.4px);background:transparent;color:var(--ui-text-primary);cursor:pointer}
.wa-job-act:not(:disabled):hover{background:var(--ui-control-hover-background)}
.wa-job-act.wa-bad{color:var(--ui-red);border-color:color-mix(in srgb,var(--ui-red) 45%,var(--ui-stroke-primary))}
.wa-job-act:disabled{opacity:.5;cursor:default}
.wa-job-act:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.wa-act-last{grid-column:3}
.wa-job-confirm{grid-column:1 / -1;margin:6px -12px 0;padding:10px 12px;border-radius:0;
  border-top:1px solid color-mix(in srgb,var(--ui-orange) 22%,transparent)}
.wa-job-sched{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;min-width:0}
.wa-job-human{font-size:12px;color:var(--ui-text-primary)}
.wa-job-cron{color:var(--ui-text-secondary);white-space:nowrap}
.wa-job-runs{display:flex;flex-wrap:wrap;align-items:center;gap:2px 14px;min-width:0;padding-top:1px}
.wa-job-run{display:inline-flex;flex-wrap:wrap;align-items:center;gap:2px 6px;min-width:0;font-size:12px}
.wa-job-runlabel{color:var(--ui-text-tertiary)}
.wa-job-runval{color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.wa-job-flag{display:inline-flex;border-radius:var(--radius-md,2px)}
.wa-job-flag:focus-visible,.wa-job-cron:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.wa-sched{gap:10px}
.wa-sched-field{display:grid;grid-template-columns:6.5rem minmax(0,1fr);gap:4px 10px;align-items:center;
  min-width:0}
.wa-sched-lab{font-size:12px;color:var(--ui-text-secondary)}
.wa-sched-ctl{display:flex;flex-wrap:wrap;gap:4px;align-items:center;min-width:0}
.wa-root .wa-sched-freq,.wa-root .wa-sched-every{display:grid;grid-auto-flow:row;width:100%;
  grid-template-columns:repeat(auto-fit,minmax(5.5rem,1fr))}
.wa-root .wa-sched-freq{max-width:36rem}
.wa-root .wa-sched-every{max-width:24rem}
.wa-root .wa-day{min-width:2.75rem}
.wa-root .wa-day[aria-pressed="true"]{background:color-mix(in srgb,var(--ui-accent) 24%,transparent);
  color:var(--ui-text-primary);box-shadow:inset 0 0 0 1px var(--ui-accent)}
.wa-sched-time{width:7.5rem;font-variant-numeric:tabular-nums}
.wa-sched-num{width:4.5rem;font-variant-numeric:tabular-nums}
.wa-sched-input{width:100%;max-width:220px;min-width:0;
  font-family:var(--dt-font-mono,monospace);font-size:13px}
.wa-sched-note{font-size:12px;color:var(--ui-text-secondary)}
.wa-sched-preview{display:grid;gap:3px;min-width:0;padding:8px 10px;border-radius:var(--radius-lg,2.4px);
  background:var(--hx-card);border:1px solid var(--ui-stroke-tertiary)}
.wa-sched-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;min-width:0}
.wa-sched-human{font-size:12px;font-weight:600;color:var(--ui-text-primary)}
.wa-sched-expr{color:var(--ui-text-secondary)}
.wa-sched-runs{font-size:12px;color:var(--ui-text-secondary);font-variant-numeric:tabular-nums;
  display:flex;flex-wrap:wrap;gap:2px 6px}
.wa-sched-runs.wa-bad{color:var(--ui-red)}
.wa-sched-zone{font-size:12px;color:var(--ui-text-tertiary)}
.wa-sched-acts{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:flex-end}
.wa-root .wa-sched-save{font-weight:600;color:var(--ui-text-primary);
  background:color-mix(in srgb,var(--ui-accent) 26%,transparent);box-shadow:inset 0 0 0 1px var(--ui-accent)}
.wa-root .wa-sched-save:hover{background:color-mix(in srgb,var(--ui-accent) 36%,transparent)}
.wa-job-drift{grid-column:1 / -1;font-size:12px;color:var(--ui-orange);padding-top:2px}
.wa-job-drift .wa-mono{color:inherit}
.wa-confirm{display:grid;gap:8px;padding:10px 14px;border-radius:0;border-left:2px solid var(--ui-orange);
  background:color-mix(in srgb,var(--ui-orange) 6%,transparent)}
.wa-confirm.wa-sched{border-left:0;border-top:1px solid var(--ui-stroke-tertiary);background:transparent;padding:14px 0 4px}
.wa-confirm-row{display:flex;gap:8px;align-items:center;justify-content:flex-end}
.wa-confirm-text{font-size:12px;color:var(--ui-text-secondary)}
.wa-cands{display:grid;gap:4px}
.wa-cand-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.wa-cand{display:flex;gap:8px;align-items:center;justify-content:flex-start;text-align:left;
  min-height:30px;padding:0 8px;border-radius:var(--radius-lg,2.4px);width:100%;border:0;background:transparent;
  color:inherit;font:inherit;cursor:pointer;min-width:0}
.wa-cand-row .wa-cand-path{flex:0 1 auto;text-align:left}
.wa-root .wa-filter{opacity:1;width:220px;max-width:100%;height:28px;padding:0 8px;gap:6px;
  border-width:1px;border-style:solid;border-radius:var(--radius-lg,2.4px)}
.wa-root .wa-filter-input{flex:1 1 0;min-width:0;height:26px}
.wa-cand:hover{background:var(--ui-row-hover-background)}
.wa-cand-row{display:flex;gap:8px;align-items:center;min-width:0;width:100%}
.wa-pend-item{min-width:0}
.wa-pend{display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 8px;align-items:center;
  width:100%;min-width:0;padding:6px 12px;border:0;border-top:1px solid var(--ui-stroke-tertiary);
  background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer}
.wa-pend:hover,.wa-pend[aria-expanded="true"]{background:var(--ui-row-hover-background)}
.wa-pend-target{color:var(--ui-text-primary)}
.wa-pend-sum{grid-column:1 / -1;font-size:12px;color:var(--ui-text-secondary)}
.wa-pend-body{display:grid;gap:4px;min-width:0}
.wa-pend-detail{display:grid;gap:8px;padding:8px 12px 12px;min-width:0}
.wa-pend-acts{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}
.wa-pend-why{flex:1 1 220px;min-width:140px}
@container (max-width:620px){
  .wa-job{grid-template-columns:minmax(0,1fr)}
  .wa-job-acts{justify-content:flex-start}
}
@container (max-width:470px){
  .wa-code-head{flex-wrap:wrap}
  .wa-sched-field{grid-template-columns:minmax(0,1fr)}
}
.fl-desk{display:grid;gap:12px;min-width:0}
.fl-layout{display:grid;grid-template-columns:210px minmax(0,1fr);border:1px solid var(--ui-stroke-primary);
  border-radius:var(--radius-xl,3.2px);overflow:hidden;min-width:0;background:var(--hx-card)}
.fl-index{min-width:0;padding:12px 8px;border-right:1px solid var(--ui-stroke-primary);
  background:color-mix(in srgb,var(--ui-bg-elevated) 38%,var(--hx-card))}
.fl-index-head{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:0 8px 10px}
.fl-index-head h2{font-size:12px;font-weight:500;color:var(--ui-text-secondary)}
.fl-index-scroll{max-height:${FOLIO_H.index}px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin}
.wa-root .fl-item{min-height:0;box-sizing:border-box;display:grid;grid-template-columns:1fr;gap:6px;
  align-content:start;padding:10px;margin:0 0 6px;border:1px solid transparent;border-radius:var(--radius-lg,2.4px)}
.wa-root .fl-item[aria-pressed="true"]{border-color:var(--ui-stroke-primary);background:var(--hx-card)}
.fl-item .wa-badge{justify-self:start;font-size:12px;background:transparent;color:var(--ui-text-secondary);
  border:0;padding:0;box-shadow:none}
.fl-item-kind{display:flex;align-items:center;gap:7px}.fl-item-kind .codicon{font-size:13px}
.fl-item-footer{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ui-text-secondary)}
.fl-item-footer .codicon{font-size:12px}
.fl-item .fl-item-title{font-size:13px;font-weight:600;line-height:1.5;text-transform:capitalize;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fl-item-summary{font-size:12px;line-height:1.65;color:var(--ui-text-secondary);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fl-index-note{border-top:1px solid var(--ui-stroke-primary);padding:10px 8px 0;font-size:12px;
  line-height:1.65;color:var(--ui-text-secondary)}
.fl-document{min-width:0;padding:0}
.fl-document.wa-pend-detail{display:block}
.fl-document-head{display:grid;gap:0;padding:0 0 14px;min-width:0}
.fl-document-top{display:flex;justify-content:space-between;gap:16px;padding-bottom:10px;
  border-bottom:1px solid var(--ui-stroke-primary);font-size:12px;color:var(--ui-text-secondary)}
.wa-root .fl-document-head h2{font-size:18px;font-weight:550;letter-spacing:-.03em;line-height:1.2;
  margin:12px 0 0;overflow-wrap:anywhere}
.fl-document-head .fl-summary{margin:8px 0 0;font-size:13px;line-height:1.6;
  max-width:72ch;color:var(--ui-text-secondary)}
.fl-document-head .fl-file{margin:8px 0 0;font-size:12px;line-height:1.7;
  color:var(--ui-text-secondary);overflow-wrap:anywhere}
.fl-review{display:grid;grid-template-columns:minmax(0,1fr) 210px;min-width:0}
.fl-change{min-width:0;display:grid;align-content:start;padding:16px 20px}
.fl-views{display:flex;gap:22px;border-bottom:1px solid var(--ui-stroke-primary)}
.fl-views button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;
  padding:11px 0;font:inherit;font-size:12px;color:var(--ui-text-secondary);cursor:pointer}
.fl-views button[aria-pressed="true"]{border-bottom-color:var(--ui-text-primary);color:var(--ui-text-primary)}
.fl-proposal,.fl-reason{height:${FOLIO_H.diff}px;overflow:auto;overscroll-behavior:contain;
  padding:12px 0;scrollbar-width:thin;min-width:0}
.fl-line{display:grid;grid-template-columns:23px minmax(0,1fr);gap:16px;min-width:0;line-height:1.8}
.fl-gutter{font:12px/1.8 ui-monospace,monospace;text-align:center;color:var(--ui-text-secondary)}
.fl-line[data-change="added"] .fl-gutter{background:color-mix(in srgb,var(--ui-green) 10%,transparent)}
.fl-line[data-change="removed"] .fl-gutter{background:color-mix(in srgb,var(--ui-red) 10%,transparent)}
.fl-line-heading{font-size:18px;font-weight:600;padding-bottom:10px;overflow-wrap:anywhere}
.fl-line-heading[data-level="2"]{font-size:16px;padding:8px 0 7px}
.fl-line-heading[data-level="3"],.fl-line-heading[data-level="4"],.fl-line-heading[data-level="5"],
.fl-line-heading[data-level="6"]{font-size:13px;padding:6px 0;font-weight:600}
.fl-line-text{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}
.fl-original{font-size:12px;margin-top:18px;color:var(--ui-text-secondary)}
.fl-original summary{cursor:pointer;padding:8px 0}
.fl-original .wa-raw [data-slot="panel-block"]{max-height:180px;overflow:auto}
.fl-reason h3{font-size:13px;margin:0 0 10px}
.fl-reason p{font-size:13px;line-height:1.75;margin:0 0 24px;overflow-wrap:anywhere}
.fl-checks{display:flex;justify-content:space-between;gap:16px;padding:10px 0;font-size:12px;
  border-top:1px solid var(--ui-stroke-primary);border-bottom:1px solid var(--ui-stroke-primary);
  color:var(--ui-text-secondary)}
.fl-approval{display:grid;gap:10px;padding-top:12px}
.fl-decision{display:grid;gap:14px;align-content:start;min-width:0;padding:16px 14px;
  border-left:1px solid var(--ui-stroke-primary);
  background:color-mix(in srgb,var(--ui-bg-elevated) 38%,var(--hx-card))}
.fl-decision h3{font-size:12px;font-weight:600}
.fl-trail{list-style:none;padding:0;margin:0;display:grid}
.fl-trail li{display:grid;grid-template-columns:19px minmax(0,1fr);gap:9px;position:relative;padding:0 0 12px}
.fl-trail li:not(:last-child):before{content:'';position:absolute;left:9px;top:19px;bottom:0;
  border-left:1px solid var(--ui-stroke-primary)}
.fl-trail li:last-child{padding-bottom:0}.fl-trail-point{width:19px;height:19px;border-radius:50%;
  border:1px solid var(--ui-stroke-primary);display:grid;place-items:center;color:var(--ui-text-secondary)}
.fl-trail-point .codicon{font-size:12px}.fl-trail li:last-child .fl-trail-point{background:var(--wa-card,var(--dt-card))}
.fl-trail-copy{display:grid;gap:2px;min-width:0}.fl-trail-copy strong{font-size:12px;font-weight:600;line-height:1.7}
.fl-trail-copy>span{font-size:12px;line-height:1.7;overflow-wrap:anywhere;color:var(--ui-text-secondary)}
.fl-facts{max-height:${FOLIO_H.facts}px;overflow-y:auto;overflow-wrap:anywhere;scrollbar-width:thin}
.fl-facts .wa-kv{display:grid;grid-template-columns:minmax(0,1fr);gap:0}
.fl-facts dt{font-size:12px;font-weight:600;color:var(--ui-text-primary);padding:12px 0 6px;
  border-top:1px solid var(--ui-stroke-primary)}
.fl-facts dt:first-child{padding-top:10px}
.fl-approval .wa-pend-acts>[data-slot="button"]{border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-lg,2.4px);
  background:transparent;color:var(--ui-text-primary);box-shadow:none}
.fl-approval .wa-pend-acts>[data-slot="button"]:last-child{background:var(--ui-text-primary);color:var(--ui-bg-sidebar);
  border-color:var(--ui-text-primary)}
.fl-approval .wa-pend-acts>[data-slot="button"]:not(:disabled):hover{filter:brightness(.94)}
.fl-facts dd{margin:0 0 12px;font-size:12px;line-height:1.7;color:var(--ui-text-secondary)}
.fl-destination{display:grid;gap:7px}
.fl-warning{margin:0;font-size:12px;line-height:1.6;color:var(--ui-text-secondary);overflow-wrap:anywhere}
.fl-confirm{min-width:0;display:grid;gap:8px}.fl-confirm p{margin:0;overflow-wrap:anywhere}
.fl-confirm .wa-raw [data-slot="panel-block"]{max-height:${FOLIO_H.dryRun}px}
.wa-root .fl-item:focus-visible,.fl-proposal:focus-visible,.fl-views button:focus-visible{
  outline:2px solid var(--ui-accent);outline-offset:-3px}
@container (max-width:850px){.fl-review{grid-template-columns:minmax(0,1fr)}
  .fl-decision{border-left:0;border-top:1px solid var(--ui-stroke-primary);padding:18px 24px}
  .fl-facts{max-height:210px}.fl-facts .wa-kv{grid-template-columns:100px minmax(0,1fr);gap:12px}
  .fl-facts dt{border:0;padding:0}.fl-facts dd{margin:0}.fl-change{padding:16px}}
@container (max-width:620px){.fl-layout{grid-template-columns:minmax(0,1fr)}
  .fl-index{border-right:0;border-bottom:1px solid var(--ui-stroke-primary)}
  .fl-index-scroll{max-height:${FOLIO_H.indexNarrow}px}
  .fl-index-note{display:none}.fl-change{padding:14px 16px}.wa-root .fl-document-head h2{font-size:18px}}
.wa-root h1,.wa-root h2,.wa-root h3{margin:0}
.g-panel{border:0;border-top:1px solid var(--ui-stroke-tertiary);border-radius:0;overflow:hidden;min-width:0}
.g-panel-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:20px 0 16px;
  border-bottom:1px solid var(--ui-stroke-tertiary)}
.g-panel-title{font-size:14px;font-weight:600;color:var(--ui-text-primary)}
.g-dot{width:8px;height:8px;border-radius:50%;background:var(--ui-text-quaternary)}
.g-dot[data-tone="ok"]{background:var(--ui-green)}
.g-dot[data-tone="bad"]{background:var(--ui-red)}
.g-dot[data-tone="warn"]{background:var(--ui-orange)}
@property --nx-angle{syntax:'<angle>';inherits:false;initial-value:0deg}
.wa-recovery-unread{display:grid;gap:6px;min-width:0}
.wa-recovery-unread>.wa-body{padding:0}
.g-panel .wa-job{display:block;padding:0}
.wa-job-summary{display:grid;grid-template-columns:29px minmax(0,1.2fr) minmax(0,1fr) 9.5rem 12px;
  gap:12px;align-items:center;min-height:52px;padding:10px 0;list-style:none;cursor:pointer;color:var(--ui-text-primary)}
.wa-job-summary::-webkit-details-marker{display:none}.wa-job-summary:hover{background:var(--ui-row-hover-background)}
.wa-job-summary:focus-visible{outline:2px solid var(--ui-accent);outline-offset:-2px}
.wa-job-summary>strong{font-size:12px;font-weight:550;min-width:0;overflow-wrap:anywhere}
.wa-job-summary-schedule{font-size:12px;color:var(--ui-text-secondary);line-height:1.6}
.wa-job-summary-state{font-size:12px;color:var(--ui-text-secondary);display:flex;gap:6px;align-items:center;justify-content:flex-end}
.wa-job-summary-state[data-tone="bad"]:before{content:'';width:5px;height:5px;border-radius:50%;background:var(--ui-red);flex-shrink:0}
.wa-job-glyph,.wa-job-summary>.codicon{color:var(--ui-text-secondary);font-size:13px}
.wa-job[open]>.wa-job-summary>.codicon{transform:rotate(180deg)}
.wa-job-expanded{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:6px 0 18px}
.wa-job-expanded .wa-job-confirm{margin:6px 0 0}
.wa-job-expanded .wa-job-name{display:none}
.wa-jobs-count{white-space:nowrap}
.wa-job-glyph{width:29px;height:29px;box-sizing:border-box;border:1px solid var(--ui-stroke-secondary);border-radius:var(--radius-lg,2.4px);
  display:grid;place-items:center}
@container (max-width:650px){
  .wa-job-summary{grid-template-columns:29px minmax(0,1fr) auto 12px;gap:10px}
  .wa-job-summary-schedule{display:none}.wa-job-expanded{grid-template-columns:minmax(0,1fr)}
  .wa-job-expanded .wa-job-acts{justify-self:start}
}
@container (max-width:470px){
  .g-panel-head{flex-wrap:wrap}
}
:root:not(.dark) .wa-root .wa-danger,:root:not(.dark) .wa-root .wa-bad,:root:not(.dark) .wa-root .wa-msg[data-tone="bad"]{
  color:color-mix(in srgb,var(--ui-red) 65%,var(--ui-text-primary))}
:root:not(.dark) .wa-root .wa-badge[data-status-tone="success"]{
  color:color-mix(in srgb,var(--ui-green) 60%,var(--ui-text-primary))}
:root:not(.dark) .wa-root .wa-badge[data-status-tone="warn"],:root:not(.dark) .wa-root .wa-job-drift{
  color:color-mix(in srgb,var(--ui-orange) 50%,var(--ui-text-primary))}
.wa-metro{container-type:inline-size}
.wa-metro-kept{display:none}
.wa-root.wa-metro{gap:0;padding:0 0 24px;container-type:inline-size}
.wa-metro{--wa-card:var(--ui-bg-card,var(--ui-surface-background))}
.wa-metro-head{display:flex;align-items:center;gap:10px;padding:14px 24px;border-bottom:1px solid var(--ui-stroke-tertiary)}
.wa-metro-head h1{font-size:14px;font-weight:600;margin:0;min-width:0;flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wa-metro-nav{display:flex;gap:6px;align-items:center;flex:none}
.wa-metro-navbtn{font:inherit;font-size:13px;display:inline-flex;gap:6px;align-items:center;padding:5px 10px;border-radius:var(--radius-xl,3.2px);
  border:1px solid var(--ui-stroke-secondary);background:transparent;color:var(--ui-text-primary);cursor:pointer;
  transition:${move('hover', 'background-color, border-color')}}
.wa-metro-navbtn:hover{background:var(--ui-control-hover-background)}
.wa-metro-navbtn[aria-pressed="true"]{border-color:var(--ui-accent);background:var(--ui-row-active-background)}
.wa-metro-navbtn:focus-visible,.wa-metro-station:focus-visible,.wa-metro-line:focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}
.wa-metro-map{position:relative;padding:24px 36px 18px;min-width:0}
.wa-metro-wires{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible;z-index:0}
.wa-metro-wire{fill:none;stroke-linecap:round;stroke:var(--ui-text-primary);stroke-width:8;transition:${move('hover', 'stroke, opacity')}}
.wa-metro-wire[data-kind="seg"][data-state="dim"]{stroke:var(--ui-text-tertiary);opacity:.55}
.wa-metro-wire[data-kind="seg"][data-state="off"]{stroke:var(--ui-red);stroke-dasharray:2 12}
.wa-metro-wire[data-kind][data-state="unknown"]{stroke:var(--ui-text-tertiary);stroke-dasharray:3 9;opacity:.6}
.wa-metro-wire[data-kind="line"]{stroke:var(--wa-hue);stroke-width:5}
.wa-metro-wire[data-kind="line"][data-state="missing"],.wa-metro-wire[data-kind="line"][data-state="off"]{stroke:var(--ui-text-tertiary);stroke-dasharray:3 7;opacity:.7}
.wa-metro-wire[data-kind="line"][data-state="unread"]{stroke:var(--ui-orange);stroke-dasharray:3 7}
.wa-metro-wire[data-kind="line"][data-state="run"]{stroke-width:6;stroke-dasharray:14 6;animation:wa-metro-march ${MOTION.march.ms}ms ${MOTION.march.ease} infinite}
@keyframes wa-metro-march{to{stroke-dashoffset:-20}}
.wa-metro[data-dir="v"] .wa-metro-wire[data-kind="line"],.wa-metro-map[data-dir="v"] .wa-metro-wire[data-kind="line"]{stroke-width:4}
.wa-metro-title{position:relative;z-index:1;margin:0;font-size:20px;font-weight:700;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
.wa-metro-subtitle{color:var(--ui-text-secondary);font-weight:500;font-size:14px}
.wa-metro-grid{position:relative;display:grid;grid-template-columns:minmax(180px,330px) minmax(0,3fr);align-items:center;margin-top:22px;min-height:210px}
.wa-metro-lines{display:flex;flex-direction:column;align-items:flex-start;gap:18px;position:relative;z-index:1;min-width:0}
.wa-metro-line{display:flex;align-items:center;gap:10px;padding:0;border:0;background:transparent;color:var(--ui-text-primary);
  font:inherit;font-size:13px;font-weight:600;cursor:pointer;text-align:left;min-width:0;border-radius:var(--radius-lg,2.4px)}
.wa-metro-line-dot{width:14px;height:14px;box-sizing:border-box;border-radius:50%;border:3px solid var(--wa-hue);background:var(--wa-card);flex:none}
.wa-metro-line[data-state="missing"] .wa-metro-line-dot,.wa-metro-line[data-state="off"] .wa-metro-line-dot{border-color:var(--ui-text-tertiary);border-style:dashed}
.wa-metro-line[data-state="missing"] .wa-metro-line-name,.wa-metro-line[data-state="off"] .wa-metro-line-name{color:var(--ui-text-secondary)}
.wa-metro-line[data-state="unread"] .wa-metro-line-dot{border-color:var(--ui-orange);border-style:dashed}
.wa-metro-line-text{display:inline-flex;align-items:baseline;flex-wrap:wrap;gap:2px 10px;min-width:0;padding-right:8px}
.wa-metro-line-note{font-weight:500;font-size:12px;color:var(--ui-text-secondary)}
.wa-metro-line[aria-pressed="true"] .wa-metro-line-name{text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:2px}
.wa-metro-stations{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:start;min-width:0}
.wa-metro-station{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;
  padding:4px 6px;border:0;background:transparent;color:var(--ui-text-primary);font:inherit;cursor:pointer;min-width:0;border-radius:var(--radius-xl,3.2px)}
.wa-metro-copy{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
.wa-metro-stop{width:30px;height:30px;box-sizing:border-box;border-radius:50%;border:5px solid var(--ui-text-primary);background:var(--wa-card);flex:none;
  transition:${move('hover', 'border-color, box-shadow')}}
.wa-metro-station[data-state="warn"] .wa-metro-stop{border-color:var(--ui-orange);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-orange) 22%,transparent)}
.wa-metro-station[data-state="bad"] .wa-metro-stop{border-color:var(--ui-red);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-red) 22%,transparent)}
.wa-metro-station[data-state="ask"] .wa-metro-stop{border-color:var(--ui-accent);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-accent) 25%,transparent)}
.wa-metro-station[data-state="run"] .wa-metro-stop{border-color:var(--ui-accent);border-top-color:transparent}
.wa-metro-station[data-state="paused"] .wa-metro-stop{border-color:var(--ui-orange);border-style:dashed}
.wa-metro-station[aria-pressed="true"] .wa-metro-name{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:2px}
.wa-metro-station[aria-pressed="true"] .wa-metro-stop{outline:2px solid var(--ui-text-primary);outline-offset:7px}
.wa-metro-name{font-size:14px;font-weight:700}
.wa-metro-text{font-size:13px;color:var(--ui-text-secondary);line-height:1.45;overflow-wrap:anywhere}
.wa-metro-pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:0 10px;height:24px;box-sizing:border-box;border-radius:9999px;white-space:nowrap;
  color:var(--ui-text-primary);border:1px solid var(--ui-accent);background:color-mix(in srgb,var(--ui-accent) 24%,var(--wa-card))}
.wa-metro-pill[data-empty]{visibility:hidden;padding:0;border:0}
.wa-metro-pill[data-tone="bad"]{border-color:var(--ui-red);background:color-mix(in srgb,var(--ui-red) 24%,var(--wa-card))}
.wa-metro-pill[data-tone="warn"]{border-color:var(--ui-orange);background:color-mix(in srgb,var(--ui-orange) 24%,var(--wa-card))}
.wa-metro-pill .codicon{font-size:12px}
.wa-metro-bone{display:block;border-radius:var(--radius-xl,3.2px);background:color-mix(in srgb,var(--ui-text-primary) 8%,transparent)}
.wa-metro-bone[data-shape="line"]{height:16px;width:140px}
.wa-metro-bone[data-shape="stop"]{width:30px;height:30px;border-radius:50%}
.wa-metro-bone[data-shape="name"]{width:90px;height:14px}
.wa-metro-bone[data-shape="text"]{width:140px;max-width:100%;height:12px}
.wa-metro-bones{display:flex;flex-direction:column;align-items:center;gap:10px;min-width:0}
.wa-metro-bar{margin:4px 36px 22px;display:flex;gap:14px;align-items:center;padding:14px 18px;border-radius:var(--radius-xl,3.2px);min-width:0;
  border-left:5px solid var(--wa-tone,var(--ui-accent));background:color-mix(in srgb,var(--wa-tone,var(--ui-accent)) 12%,transparent)}
.wa-metro-bar[data-tone="warn"]{--wa-tone:var(--ui-orange)}
.wa-metro-bar[data-tone="bad"]{--wa-tone:var(--ui-red)}
.wa-metro-bar[data-tone="ok"]{--wa-tone:var(--ui-green)}
.wa-metro-bar[data-tone="ask"]{--wa-tone:var(--ui-accent)}
.wa-metro-bar-icon{color:var(--wa-tone);font-size:20px;display:grid;place-items:center;flex:none}
.wa-metro-bar-icon .codicon{font-size:20px}
.wa-metro-bar-copy{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 auto}
.wa-metro-bar-head{font-weight:700;font-size:13px;overflow-wrap:anywhere}
.wa-metro-bar-text{color:var(--ui-text-secondary);font-size:13px;overflow-wrap:anywhere}
.wa-root .wa-metro-bar-act{flex:none;margin-left:auto;border-color:var(--wa-tone);
  background:color-mix(in srgb,var(--wa-tone) 55%,transparent);color:var(--ui-text-primary);font-weight:600}
.wa-root .wa-metro-bar-act:hover{background:color-mix(in srgb,var(--wa-tone) 68%,transparent)}
.wa-metro-detail{margin:0 36px 24px;border:1px solid var(--ui-stroke-secondary);border-radius:var(--radius-xl,3.2px);overflow:hidden;min-width:0}
.wa-metro-dhead{display:flex;align-items:center;gap:10px;padding:10px 12px 10px 18px;border-bottom:1px solid var(--ui-stroke-tertiary);
  background:color-mix(in srgb,var(--ui-bg-elevated) 60%,transparent)}
.wa-metro-dhead h2{font-weight:700;font-size:14px;margin:0;flex:1 1 auto;min-width:0;overflow-wrap:anywhere}
.wa-metro-dbody{padding:16px 18px;display:flex;flex-direction:column;gap:12px;min-width:0}
.wa-metro-lead{font-weight:700;font-size:13px}
.wa-metro-sub{margin:4px 0 0;font-size:13px;font-weight:600;color:var(--ui-text-secondary)}
.wa-metro-findings{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.wa-metro-finding{display:grid;grid-template-columns:22px minmax(0,1fr);gap:10px;padding:9px 0;border-top:1px solid var(--ui-stroke-tertiary)}
.wa-metro-finding:first-child{border-top:0}
.wa-metro-finding-n{color:var(--ui-text-secondary);font-size:13px}
.wa-metro-finding-body{display:flex;flex-direction:column;gap:2px;min-width:0;font-size:13px}
.wa-metro-finding-body p{margin:0;color:var(--ui-text-secondary);font-size:12px;overflow-wrap:anywhere}
.wa-metro-raw summary{cursor:pointer;font-size:12px;color:var(--ui-text-secondary);padding:2px 0}
.wa-metro-raw [data-slot="panel-block"]{font-size:12px;overflow-wrap:anywhere;white-space:pre-wrap}
.wa-metro-acts{display:flex;gap:8px 12px;flex-wrap:wrap;align-items:center}
.wa-root .wa-metro-ask{border-color:var(--ui-orange);background:color-mix(in srgb,var(--ui-orange) 26%,transparent);color:var(--ui-text-primary);font-weight:600}
.wa-metro-note{margin:0;font-size:12px;color:var(--ui-text-secondary);display:flex;gap:8px;align-items:flex-start}
.wa-metro-note .codicon{font-size:14px;flex:none}
.wa-metro-jobs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.wa-metro-job{border:1px solid var(--ui-stroke-tertiary);border-radius:var(--radius-xl,3.2px);padding:10px 12px;min-width:0}
.wa-metro-job-head{display:flex;gap:8px;align-items:center;font-weight:600;font-size:13px}
.wa-metro-job p{margin:4px 0 0;font-size:12px;color:var(--ui-text-secondary);line-height:1.45}
.wa-metro-dot{width:10px;height:10px;border-radius:50%;background:var(--ui-text-quaternary);flex:none}
.wa-metro-dot[data-tone="ok"]{background:var(--ui-green)}
.wa-metro-dot[data-tone="warn"]{background:var(--ui-orange)}
.wa-metro-dot[data-tone="bad"]{background:var(--ui-red)}
.wa-metro-dot[data-tone="ask"]{background:var(--ui-accent)}
.wa-metro-runs{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.wa-metro-run{display:grid;grid-template-columns:132px 22px minmax(0,1fr) auto;gap:4px 12px;align-items:center;
  padding:10px 0;border-top:1px solid var(--ui-stroke-tertiary)}
.wa-metro-run:first-child{border-top:0;padding-top:2px}
.wa-metro-run-at{font-size:12px;color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.wa-metro-run-glyph{display:inline-flex;justify-content:center;color:var(--ui-text-secondary)}
.wa-metro-run-what{display:flex;flex-direction:column;gap:2px;min-width:0;font-size:13px;overflow-wrap:anywhere}
.wa-metro-run-what span{font-size:12px;color:var(--ui-text-secondary)}
.wa-metro-run-out{display:inline-flex;gap:8px;align-items:center;justify-self:end;text-align:right;font-size:13px}
.wa-metro-techlog{border-top:1px solid var(--ui-stroke-tertiary);padding-top:12px;min-width:0}
.wa-metro-jobctl{display:flex;flex-direction:column;gap:10px;min-width:0}
.wa-metro-kv{font-size:13px}
.wa-metro-error p{margin:0;font-size:13px}
.wa-metro-sec{display:flex;flex-direction:column;gap:8px;min-width:0}
.wa-metro-sec+.wa-metro-sec{border-top:1px solid var(--ui-stroke-tertiary);padding-top:14px}
.wa-metro-sec .wa-job,.wa-metro-dbody .wa-job{display:block;padding:0}
.wa-metro-dbody>.wa-shell,.wa-metro-dbody .pa-root{height:auto!important;overflow:visible!important}
.wa-desk{display:flex;flex-direction:column;gap:12px;min-width:0}
.wa-desk-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wa-desk-kind{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 8px;border-radius:var(--radius-lg,2.4px);border:1px solid var(--ui-stroke-secondary)}
.wa-desk-steps{display:flex;gap:6px;align-items:center;margin-left:auto;color:var(--ui-text-secondary);font-size:12px}
.wa-desk-step{width:8px;height:8px;border-radius:50%;background:var(--ui-stroke-secondary);display:inline-block}
.wa-desk-step[data-on]{background:var(--ui-accent)}
.wa-desk-title{margin:0;font-size:20px;font-weight:700;overflow-wrap:anywhere;text-transform:none}
.wa-desk-title::first-letter{text-transform:uppercase}
.wa-desk-summary{margin:4px 0 0;color:var(--ui-text-secondary);font-size:14px}
.wa-desk-path{margin:0;color:var(--ui-text-secondary);overflow-wrap:anywhere}
.wa-desk-acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.wa-requests{display:flex;flex-direction:column;gap:10px;min-width:0}
.wa-requests>.wa-desk-summary{margin:0}
.wa-request{padding:2px 0 2px 12px;border-left:2px solid var(--ui-stroke-secondary);min-width:0;overflow-wrap:anywhere;font-size:14px}
.wa-request[data-state="fetched"]{border-left-color:var(--ui-green)}
.wa-request[data-state="failed"]{border-left-color:var(--ui-red)}
.wa-request-head{margin:0 0 4px;display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.wa-request-state{color:var(--ui-text-secondary)}
.wa-request[data-state="fetched"] .wa-request-state{color:var(--ui-green)}
.wa-request[data-state="failed"] .wa-request-state{color:var(--ui-red)}
.wa-request-source,.wa-request-passage{display:block}
.wa-request-passage{font-style:italic;color:var(--ui-text-primary)}
.wa-sha-short{display:none}
.wa-refusal{display:flex;flex-direction:column;gap:4px;overflow-wrap:anywhere}
.wa-refusal>p{margin:0}
.wa-refusal-head{font-weight:600}
.wa-desk-row{display:flex;flex-wrap:wrap;gap:10px 20px;align-items:center;min-width:0}
.wa-desk-row>.wa-desk-more[open]{flex:1 1 100%}
.wa-approve{display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--ui-text-primary)}
.wa-approve p{margin:0}
.wa-approve-path{font-weight:600;overflow-wrap:anywhere}
.wa-approve-warn{display:flex;gap:8px;align-items:flex-start;color:var(--ui-text-secondary)}
.wa-approve-warn .codicon{color:var(--ui-red);margin-top:1px}
.wa-metro-bar-raw{margin-top:6px}
.wa-desk-acts .wa-confirm{flex:1 1 100%;order:-1;max-width:640px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.wa-desk-acts .wa-confirm>input,.wa-desk-acts .wa-confirm>[data-slot=input]{flex:1 1 280px}
.wa-desk-acts .wa-confirm .wa-pend-acts{flex:0 0 auto}
.wa-desk-row:has(>.wa-desk-acts>.wa-confirm){flex-wrap:wrap}
.wa-desk-acts:has(>.wa-confirm){flex:1 1 100%}
.wa-desk-more>summary{cursor:pointer;font-size:13px;color:var(--ui-text-secondary);display:flex;gap:6px;align-items:center;list-style:none;padding:2px 0}
.wa-desk-more>summary::-webkit-details-marker{display:none}
.wa-desk-more>summary .codicon{transition:${move('hover', 'transform')}}
.wa-desk-more[open]>summary .codicon{transform:rotate(90deg)}
.wa-desk-more>.fl-review{margin-top:10px}
.wa-metro{--wa-r:var(--radius-xl,3.2px)}
.wa-metro-head{padding:16px 28px;border-bottom:0}
.wa-metro-head h1{font-size:16px;letter-spacing:-.01em}
.wa-metro-head>.codicon{color:var(--ui-accent)}
.wa-metro-map{margin:4px 28px 18px;padding:22px 26px 20px;border:1px solid var(--ui-stroke-tertiary);border-radius:var(--wa-r);background:var(--wa-card)}
.wa-metro-map.wa-metro-skeleton{border-style:dashed}
.wa-metro-title{font-size:20px;font-weight:650;letter-spacing:-.02em}
.wa-metro-subtitle{font-size:13px;letter-spacing:0}
.wa-metro-grid{margin-top:18px;min-height:180px}
.wa-metro-wire{stroke-width:2}
.wa-metro-wire[data-kind="line"],.wa-metro-map[data-dir="v"] .wa-metro-wire[data-kind="line"]{stroke-width:2}
.wa-metro-wire[data-kind="line"][data-state="run"]{stroke-width:2.5;stroke-dasharray:8 6}
.wa-metro-wire[data-kind="seg"][data-state="off"]{stroke-dasharray:2 8}
.wa-metro-group{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ui-text-secondary)}
.wa-metro-line-dot{width:10px;height:10px;border-width:2px}
.wa-metro-line-name{font-size:13px;font-weight:600}
.wa-metro-station{padding:12px 10px;border-radius:var(--radius-lg,2.4px);transition:${move('hover', 'background-color')}}
.wa-metro-station:hover{background:var(--ui-row-hover-background)}
.wa-metro-station[aria-pressed="true"]{background:var(--ui-row-active-background)}
.wa-metro-station[aria-pressed="true"] .wa-metro-name{text-decoration:none}
.wa-metro-station[aria-pressed="true"] .wa-metro-stop{outline-width:1.5px;outline-offset:4px}
.wa-metro-stop{width:16px;height:16px;border-width:2px}
.wa-metro-station[data-state] .wa-metro-stop{box-shadow:none}
.wa-metro-station[data-state="warn"] .wa-metro-stop{background:color-mix(in srgb,var(--ui-orange) 22%,var(--wa-card))}
.wa-metro-station[data-state="bad"] .wa-metro-stop{background:color-mix(in srgb,var(--ui-red) 22%,var(--wa-card))}
.wa-metro-station[data-state="ask"] .wa-metro-stop{background:color-mix(in srgb,var(--ui-accent) 24%,var(--wa-card))}
.wa-metro-name{font-size:14px;font-weight:650;letter-spacing:-.01em}
.wa-metro-bone[data-shape="stop"]{width:16px;height:16px}
.wa-metro-bar{margin:0 28px 18px;border-radius:var(--wa-r);border-left:0;position:relative;overflow:hidden;padding:14px 18px 14px 26px}
.wa-metro-bar::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--wa-tone,var(--ui-accent))}
.wa-metro-bar-icon{align-self:flex-start;margin-top:1px}
:root:not(.dark) .wa-root .wa-metro-bar-act{background:color-mix(in srgb,var(--wa-tone) 16%,transparent)}
:root:not(.dark) .wa-root .wa-metro-bar-act:hover{background:color-mix(in srgb,var(--wa-tone) 26%,transparent)}
.wa-metro-detail{margin:0 28px 18px;border-radius:var(--wa-r);position:relative;overflow:visible;background:var(--wa-card)}
.wa-metro-dhead{border-radius:var(--wa-r) var(--wa-r) 0 0;padding:12px 16px 12px 26px;background:transparent}
.wa-metro-dhead h2{font-size:16px;font-weight:650;letter-spacing:-.01em}
.wa-metro-dbody{padding:20px 26px}
.wa-metro-detail[data-notch]::before{content:"";position:absolute;top:-8px;left:var(--wa-notch);width:15px;height:15px;
  box-sizing:border-box;transform:translateX(-50%) rotate(45deg);border-top-left-radius:var(--radius-md,2px);background:var(--wa-card);
  border-left:1px solid var(--ui-stroke-primary);border-top:1px solid var(--ui-stroke-primary)}
.wa-globe{margin:0 28px 18px;display:grid;grid-template-columns:minmax(220px,1fr) minmax(0,1.6fr);gap:12px 28px;
  padding:22px 26px;border:1px solid var(--ui-stroke-tertiary);border-radius:var(--wa-r);background:var(--wa-card);min-width:0}
.wa-metro-dbody>.wa-globe{margin:0 0 6px;padding:0 0 16px;border:0;border-bottom:1px solid var(--ui-stroke-tertiary);border-radius:0;background:transparent}
.wa-globe-copy{display:flex;flex-direction:column;gap:10px;min-width:0;justify-content:center}
.wa-metro-dbody>.wa-globe .wa-globe-label{display:none}
.wa-globe-label{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ui-text-secondary)}
.wa-globe-head{margin:0;font-size:20px;font-weight:650;letter-spacing:-.02em;line-height:1.25;overflow-wrap:anywhere}
.wa-globe-lead{margin:0;font-size:13px;color:var(--ui-text-secondary)}
.wa-globe-list{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-direction:column;gap:2px}
.wa-globe-miss{font:inherit;color:inherit;text-align:left;background:transparent;border:0;box-sizing:border-box;width:100%;display:grid;
  grid-template-columns:24px minmax(0,1fr);gap:2px 10px;align-items:center;padding:8px 10px;border-radius:var(--radius-lg,2.4px);cursor:pointer;
  transition:${move('hover', 'background-color')}}
.wa-globe-miss:hover,.wa-globe-miss[aria-pressed="true"]{background:color-mix(in srgb,var(--ui-orange) 12%,transparent)}
.wa-globe-miss:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.wa-globe-n{grid-row:span 2;width:24px;height:24px;box-sizing:border-box;border-radius:50%;border:1.5px dashed var(--ui-orange);
  display:grid;place-items:center;font-size:12px;font-weight:600}
.wa-globe-name{font-family:var(--dt-font-mono,monospace);font-size:13px;font-weight:600;overflow-wrap:anywhere}
.wa-globe-by{font-size:12px;color:var(--ui-text-secondary);overflow-wrap:anywhere}
.wa-globe-key{display:grid;grid-template-columns:repeat(2,max-content);gap:6px 24px;font-size:12px;color:var(--ui-text-secondary);margin-top:6px}
.wa-globe-key span{display:inline-flex;align-items:center;gap:6px}
.wa-globe-key i{display:inline-block;width:10px;height:10px;box-sizing:border-box;border-radius:50%;background:var(--ui-text-primary)}
.wa-globe-key i[data-k="older"]{opacity:.45}
.wa-globe-key i[data-k="names"]{background:var(--ui-orange)}
.wa-globe-key i[data-k="missing"]{background:transparent;border:1.5px dashed var(--ui-orange);width:12px;height:12px}
.wa-globe-hint{margin:0;font-size:12px;color:var(--ui-text-secondary)}
.wa-globe-stage{position:relative;min-height:400px;min-width:0}
.wa-globe-canvas{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;touch-action:none}
.wa-globe-canvas[data-drag]{cursor:grabbing}
.wa-globe-band{position:absolute;transform:translateY(-50%);display:flex;flex-direction:column;gap:1px;font-size:12px;
  color:var(--ui-text-secondary);white-space:nowrap;pointer-events:none}
.wa-globe-band b{color:var(--ui-text-primary);font-weight:600;margin-right:6px}
.wa-globe-band [data-warn]{display:inline-flex;align-items:center;gap:6px}
.wa-globe-band [data-warn]::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--ui-orange)}
.wa-globe-ring{position:absolute;transform:translate(-50%,-50%);font-size:12px;font-weight:600;pointer-events:none}
.wa-globe-tip{position:absolute;transform:translate(-50%,calc(-100% - 12px));padding:6px 10px;border-radius:var(--radius-md,2px);z-index:2;
  background:var(--ui-bg-elevated);border:1px solid var(--ui-stroke-secondary);font-size:12px;pointer-events:none;
  max-width:280px;display:flex;flex-direction:column;gap:2px}
.wa-globe-tip span{color:var(--ui-text-secondary)}
.wa-metro-text{text-wrap:balance}
.wa-metro-line{padding:4px 8px;margin:-4px -8px;border-radius:var(--radius-md,2px);transition:${move('hover', 'background-color')}}
.wa-metro-line:hover{background:var(--ui-row-hover-background)}
.wa-metro-line[aria-pressed="true"]{background:var(--ui-row-active-background)}
.wa-metro-line[aria-pressed="true"] .wa-metro-line-name{text-decoration:none}
.wa-metro-line-name,.wa-metro-line-note{line-height:1.25}
.wa-metro-line[data-state] .wa-metro-line-dot{border-style:solid}
.wa-metro-line[data-state="missing"] .wa-metro-line-dot{border-color:var(--ui-text-secondary);background:transparent}
.wa-metro-line[data-state="off"] .wa-metro-line-dot{border-color:var(--ui-text-tertiary);background:transparent;opacity:.7}
.wa-metro-line[data-state="off"] .wa-metro-line-name{color:var(--ui-text-tertiary)}
.wa-metro-line[data-state="unread"] .wa-metro-line-dot{border-color:var(--ui-orange);background:color-mix(in srgb,var(--ui-orange) 22%,var(--wa-card))}
.wa-metro-wire[data-kind="line"][data-state="missing"]{stroke:var(--ui-text-secondary);stroke-dasharray:7 5;opacity:.9}
.wa-metro-wire[data-kind="line"][data-state="off"]{stroke:var(--ui-text-tertiary);stroke-dasharray:.5 6;opacity:.75}
.wa-metro-wire[data-kind="line"][data-state="unread"]{stroke-dasharray:7 5}
:root:not(.dark) .wa-metro-wire[data-kind="line"]:not([data-state="missing"],[data-state="off"],[data-state="unread"]){
  stroke:color-mix(in srgb,var(--wa-hue) 72%,var(--ui-text-primary))}
:root:not(.dark) .wa-metro-line:not([data-state="missing"],[data-state="off"],[data-state="unread"]) .wa-metro-line-dot{
  border-color:color-mix(in srgb,var(--wa-hue) 72%,var(--ui-text-primary))}
.wa-root .wa-metro-dbody .wa-metro-sec.g-panel{border:1px solid var(--ui-stroke-tertiary);border-radius:var(--radius-xl,3.2px);
  background:transparent;padding:0;position:relative;overflow:hidden;gap:0}
.wa-root .wa-metro-dbody .wa-metro-sec.g-panel+.wa-metro-sec.g-panel{padding-top:0;border-top:1px solid var(--ui-stroke-tertiary)}
.wa-root .wa-metro-dbody .wa-metro-sec[data-need]::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--ui-accent);z-index:1}
.wa-metro-dbody .wa-metro-sec .g-panel-head{display:flex;align-items:center;gap:10px;padding:12px 18px;margin:0;
  border-bottom:1px solid var(--ui-stroke-tertiary)}
.wa-metro-dbody .wa-metro-sec .g-panel-head>.codicon{color:var(--ui-text-secondary);font-size:16px}
.wa-metro-dbody .wa-metro-sec .g-panel-title{font-size:14px;font-weight:600;margin:0}
.wa-metro-dbody .wa-metro-sec .g-panel-head>:last-child:not(.g-panel-title){margin-left:auto}
.wa-metro-dbody .wa-metro-secbody{padding:0}
.wa-metro-dbody .wa-metro-secbody .wa-body{display:block;padding:0;gap:0}
.wa-metro-dbody .wa-metro-secbody .wa-kv{display:grid;grid-template-columns:var(--wa-set-label) minmax(0,1fr);gap:4px 20px;
  margin:0;padding:12px 18px;font-size:13px}
.wa-metro-dbody .wa-metro-secbody .wa-kv+.wa-kv,.wa-set-row+.wa-kv,.wa-kv+.wa-set-row,.wa-set-row+.wa-set-row,
.wa-metro-dbody .wa-metro-secbody .wa-body>.wa-body>:first-child:not(:only-child){border-top:1px solid var(--ui-stroke-tertiary)}
.wa-metro-dbody .wa-metro-secbody .wa-kv dt,.wa-metro-dbody .wa-metro-secbody .wa-kv>div>:first-child{font-weight:600;color:var(--ui-text-primary)}
.wa-metro-dbody .wa-metro-sec{--wa-set-label:clamp(220px,32%,340px)}
.wa-set-row{display:grid;grid-template-columns:var(--wa-set-label) minmax(0,1fr) auto;gap:8px 20px;align-items:center;
  padding:12px 18px;min-height:44px}
.wa-set-name{font-size:13px;font-weight:600;color:var(--ui-text-primary)}
.wa-set-note{font-size:12px;line-height:1.45;color:var(--ui-text-secondary);margin-top:2px}
.wa-set-note .wa-engine-notes{display:flex;flex-direction:column;gap:2px}
.wa-set-value{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;font-size:13px;min-width:0}
.wa-set-value>input{width:100%}
.wa-set-acts{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;align-items:center}
.wa-set-row .wa-set-value:empty{display:none}
.wa-set-row:has(.wa-set-value:empty){grid-template-columns:minmax(0,1fr) auto}
.wa-metro-dbody .wa-metro-secbody .wa-body>.wa-body+.wa-body{border-top:1px solid var(--ui-stroke-tertiary)}
.wa-engine-rev{display:inline-flex;gap:8px;align-items:baseline}
.wa-engine-next{font-size:12px;color:var(--ui-text-secondary)}
.wa-set-chip{display:inline-flex;align-items:center;gap:6px;height:20px;padding:0 8px;border-radius:9999px;font-size:12px;font-weight:600;
  color:var(--ui-text-primary);background:color-mix(in srgb,var(--wa-tone) 16%,transparent);white-space:nowrap}
.wa-set-chip::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--wa-tone)}
.wa-set-chip[data-chip=ok]{--wa-tone:var(--ui-green)}.wa-set-chip[data-chip=ask]{--wa-tone:var(--ui-accent)}
.wa-set-chip[data-chip=warn]{--wa-tone:var(--ui-orange)}.wa-set-chip[data-chip=bad]{--wa-tone:var(--ui-red)}
.wa-metro-dbody .wa-metro-secbody>.wa-body>.wa-live:empty,.wa-metro-dbody .wa-metro-secbody .wa-live:empty{display:none}
.wa-metro-dbody .wa-metro-secbody .wa-live:not(:empty),.wa-metro-dbody .wa-metro-secbody .wa-engine-plan,
.wa-metro-dbody .wa-metro-secbody .wa-help,.wa-metro-dbody .wa-metro-secbody .wa-cands{margin:0 18px 12px}
.wa-metro-dbody .wa-metro-secbody .wa-confirm{margin:0 18px 12px}
.wa-metro-dbody .wa-metro-secbody .wa-job .wa-confirm{margin:8px 0 0}
.wa-metro-dbody .wa-metro-secbody .wa-msg{padding:10px 18px;margin:0}
.wa-metro-dbody .wa-metro-secbody .wa-msg+.wa-job,.wa-metro-dbody .wa-metro-secbody .wa-live+.wa-job{border-top:1px solid var(--ui-stroke-tertiary)}
.wa-metro-dbody .wa-jobs-count{font-size:12px;color:var(--ui-text-secondary);margin-left:auto}
.wa-metro-dbody .wa-job+.wa-job{border-top:1px solid var(--ui-stroke-tertiary)}
.wa-metro-dbody .wa-job-summary{padding:10px 18px}
.wa-metro-dbody .wa-job-summary>strong{font-size:13px;font-weight:600}
.wa-metro-dbody .wa-job-summary-schedule{font-size:13px}
.wa-metro-dbody .wa-job[open]>.wa-job-summary,.wa-metro-dbody .wa-job[open]>.wa-job-expanded{background:var(--ui-row-active-background)}
.wa-metro-dbody .wa-job-expanded{padding:4px 18px 16px 59px}
.wa-metro-dbody .wa-sched-preview{border:0;border-left:2px solid var(--ui-accent);border-radius:0;background:transparent;padding:4px 12px}
.wa-metro-dbody .wa-path-input{border:1px solid var(--ui-stroke-secondary);border-radius:var(--radius-md,2px)}
.wa-metro-dbody .wa-path-input::placeholder{color:var(--ui-text-tertiary);opacity:1}
:root.dark .wa-metro-dbody .wa-sched-time::-webkit-calendar-picker-indicator{filter:invert(.85)}
.wa-metro-dbody .wa-desk-kind{border-radius:999px;padding:2px 10px}
.wa-metro-dbody .wa-desk.wa-pend-detail{padding:0}
.wa-root .wa-metro-dbody .pa-health>.pa-sec,.wa-root .wa-metro-dbody .pa-health>.pa-kpis,
.wa-root .wa-metro-dbody .pa-health .pa-logwrap{background:transparent}
.wa-metro-dbody .wa-desk-step{background:var(--ui-text-tertiary)}
.wa-metro-dbody .wa-desk-step[data-on]{background:var(--ui-accent)}
.wa-metro-dbody .wa-refusal{border-left:2px solid var(--ui-orange);padding:2px 0 2px 14px;max-width:80ch}
.wa-metro-dbody .wa-refusal-head{font-size:14px;font-weight:650;color:var(--ui-text-primary)}
.wa-metro-dbody .wa-refusal>p{font-size:13px;line-height:1.5}
.wa-metro-dbody .wa-request-state{font-size:12px;font-weight:600}
:root:not(.dark) .wa-metro-dbody .wa-request[data-state="fetched"] .wa-request-state{color:color-mix(in srgb,var(--ui-green) 65%,var(--ui-text-primary))}
.wa-metro-dbody .wa-approve-path{font-weight:500}
.wa-metro-dbody .wa-metro-run{align-items:start}
.wa-metro-dbody .pa-health>.pa-sec,.wa-metro-dbody .pa-health>.pa-kpis{border-radius:var(--radius-lg,2.4px)}
.wa-metro-dbody .pa-health .pa-logwrap{border-radius:var(--radius-lg,2.4px)}
@container (max-width:860px){
  .wa-metro-grid{grid-template-columns:minmax(150px,240px) minmax(0,3fr)}
  .wa-metro-jobs{grid-template-columns:minmax(0,1fr)}
}
@container (max-width:640px){
  .wa-sha-full{display:none}
  .wa-sha-short{display:inline}
  .wa-metro-head{padding:12px 16px}
  .wa-metro-navlabel{display:none}
  .wa-metro-map{padding:18px 16px 12px}
  .wa-metro-title{font-size:18px;flex-direction:column;gap:4px}
  .wa-metro-grid{display:block;margin-top:16px;min-height:0}
  .wa-metro-lines{gap:12px;padding-left:52px}
  .wa-metro-line{font-size:13px}
  .wa-metro-stations{display:flex;flex-direction:column;gap:30px;margin-top:30px;padding-left:4px}
  .wa-metro-station{flex-direction:row;align-items:flex-start;text-align:left;gap:14px;padding:0}
  .wa-metro-station .wa-metro-pill{order:3;align-self:flex-start;margin-top:0}
  .wa-metro-station .wa-metro-pill[data-empty]{display:none}
  .wa-metro-station{display:grid;grid-template-columns:30px minmax(0,1fr);grid-template-areas:"stop copy" ". pill";column-gap:14px;row-gap:6px}
  .wa-metro-station .wa-metro-stop{grid-area:stop}
  .wa-metro-station .wa-metro-copy{grid-area:copy;align-items:flex-start;padding-top:2px;gap:3px}
  .wa-metro-station .wa-metro-pill{grid-area:pill;justify-self:start}
  .wa-metro-bones{flex-direction:row;align-items:center}
  .wa-metro-bar{margin:4px 16px 16px;flex-wrap:wrap;align-items:flex-start}
  .wa-metro-bar-copy{flex:1 1 calc(100% - 40px)}
  .wa-root .wa-metro-bar-act{margin-left:0;width:100%}
  .wa-metro-detail{margin:0 16px 16px}
  .wa-metro-dbody{padding:14px}
  .wa-metro-map{margin:4px 16px 16px}
  .wa-globe{grid-template-columns:minmax(0,1fr);margin:0 16px 16px;padding:16px}
  .wa-globe-stage{min-height:300px}
  .wa-metro-kv{grid-template-columns:minmax(0,1fr)}
  .wa-metro-run{grid-template-columns:22px minmax(0,1fr) auto}
  .wa-metro-run-at{grid-column:1/-1}
}
@media (prefers-reduced-motion: reduce){
  .wa-metro-navbtn,.wa-metro-wire,.wa-metro-stop,.wa-metro-station,.wa-metro-line,.wa-globe-miss,.wa-desk-more>summary .codicon{transition:none}
  .wa-metro-wire[data-kind="line"][data-state="run"]{animation:none}
}
`

const CHECKER_SOURCE = 'checker'

const _TX_MAP = [
  ['se\u00e7ilen yolun \u00fcst\u00fcnde .llm-wiki/project.json yok', 'wa.reasonDeriveNoIdentity'],
  ['.llm-wiki/project.json okunamad\u0131', 'wa.reasonIdentityUnreadable'],
  ['.llm-wiki/project.json yok', 'wa.reasonIdentityMissing'],
  ['wiki/ bo\u015f ya da kimlik eksik', 'wa.reasonWikiEmpty'],
  ['wiki/ klas\u00f6r\u00fc yok', 'wa.reasonWikiMissing'],
  ['proje k\u00f6k\u00fc bulunamad\u0131: ', 'wa.reasonRootMissing'],
  ['proje k\u00f6k\u00fc se\u00e7ilmemi\u015f', 'wa.reasonRootNotChosen'],
  ['tarama k\u00f6k\u00fc yok: ', 'wa.reasonScanRootMissing'],
  ['tarama k\u00f6k\u00fc belirsiz', 'wa.reasonScanRootUnknown'],
  ['klas\u00f6r yok', 'wa.reasonFolderMissing'],
  ['yol gerekli', 'wa.reasonPathRequired']
]

function txReason(raw, source, t) {
  const text = String(raw == null ? '' : raw).trim()
  if (!text) return null
  if (source !== CHECKER_SOURCE) return { text, raw: text, known: true }
  for (const [prefix, key] of _TX_MAP) {
    if (text.startsWith(prefix)) {
      return { text: t(key) + text.slice(prefix.length), raw: text, known: true }
    }
  }
  return { text: t('wa.checkUnrecognized'), raw: text, known: false }
}

function Loading() {
  return jsx('div', { className: 'wa-loading', children: jsx(Loader, { type: 'lemniscate-bloom' }, 'l') })
}

const failLine = (text, detail) => {
  const first = String(detail || '').trim().split(/\r?\n/)[0].trim()
  if (!first || first === text) return text
  return `${text} · ${first.length > 160 ? `${first.slice(0, 159)}…` : first}`
}

function Failure({ t, text, detail }) {
  return jsx('div', { className: 'wa-body wa-fail', children: jsxs('div', { className: 'wa-help', children: [
    jsx(ErrorState, { className: 'wa-fail-state', description: failLine(text, detail),
      icon: jsx('span', { className: 'wa-fail-dot', 'aria-hidden': true }, 'dot') }, 'e'),
    detail
      ? jsxs('details', { className: 'wa-fail-more', children: [
        jsx('summary', { children: t('wa.failDetails') }, 's'),
        jsx(Tip, { label: detail, children: jsxs('div', { className: 'wa-raw', children: [
          jsxs('div', { className: 'wa-code-head', children: [
            jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, 'c'),
            Copy({ copyKey: 'f', text: detail })
          ] }, 'ch'),
          jsx(PanelBlock, { className: 'wa-mono', children: detail }, 'p')
        ] }, 'raw') }, 'rt')
      ] }, 'more')
      : null
  ] }, 'card') })
}

function Status({ badgeKey, text, variant }) {
  const danger = variant === 'destructive'
  return jsx(Badge, { className: danger ? 'wa-badge wa-danger' : 'wa-badge',
    'data-status-tone': variant, variant, children: text }, badgeKey)
}

const toneLabel = (t, tone) => (tone === 'ok' ? t('wa.toneOk')
  : tone === 'bad' ? t('wa.toneBad')
    : tone === 'warn' || tone === 'slow' ? t('wa.toneWarn') : t('wa.toneQuiet'))

function Dot({ t, tone, className = 'g-dot' }) {
  return jsx('span', { 'aria-label': toneLabel(t, tone), className, 'data-tone': tone,
    role: 'img' })
}


const secs = (t, ms) => t('wa.durSecs', (ms / 1000).toFixed(3))

function Stale({ t, error }) {
  if (!error) return null
  return jsxs('div', { className: 'wa-stale', role: 'status', children: [
    jsx('span', { children: t('wa.staleNote') }, 'n'),
    jsx('span', { className: 'wa-mono', children: error }, 'e')
  ] }, 'stale')
}

function Copy({ copyKey, text }) {
  return jsx(CopyButton, {
    appearance: 'icon',
    buttonSize: 'icon-sm',
    buttonVariant: 'outline',
    className: 'wa-icon-btn',
    text
  }, copyKey)
}




function rootRow(t, shown, verdict) {
  return {
    label: t('wa.root'),
    value: jsxs('span', { className: 'wa-root-value', children: [
      jsx('span', { className: 'wa-mono wa-clip wa-grow', children: shown || '—' }, 'p'),
      verdict == null ? null : Status({ text: verdict ? t('wa.ok') : t('wa.invalid'),
        variant: verdict ? 'success' : 'destructive', badgeKey: 'b' }),
      shown ? Copy({ copyKey: 'c', text: shown }) : null
    ] }, 'v')
  }
}

function RootCard({ t, auto, refreshAuto }) {
  const [draft, setDraft] = useState('')
  const [msg, setMsg] = useState(null)
  const [cands, setCands] = useState(null)
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)

  const info = auto?.data || null
  const settings = info?.settings || null
  const current = settings?.project_root || ''
  const project = settings?.project || null
  const currentId = project?.id || null
  const shown = draft || current
  const unread = !auto?.scope?.fresh()
  const [forceAsk, setForceAsk] = useState(false)
  const [checked, setChecked] = useState(null)
  const forceGrant = useRef(null)
  const pathNow = useRef(shown)
  pathNow.current = shown
  const actions = usePanelActions([auto?.scope], () => {
    forceGrant.current = null
    setDraft(''); setMsg(null); setCands(null); setFilter(''); setBusy(false)
    setForceAsk(false); setChecked(null)
  })
  const changeDraft = (path, copy = false) => {
    if (!actions.matches() || !auto?.scope?.fresh()) return
    pathNow.current = path || current
    forceGrant.current = copy ? { path, scope: auto.scope.key } : null
    setDraft(path); setForceAsk(copy); setChecked(null)
  }
  const verdict = current ? Boolean(project?.ok) : null
  const draftVerdict = draft && draft !== current && checked?.path === draft ? checked.ok : null

  const normalize = path => String(path || '').replace(/[\\/]+$/, '').toLowerCase()
  const isCopy = cand => Boolean(currentId && (String(cand?.id || '') === String(currentId)
    || (cand?.duplicates || []).length))

  const say = (tone, text) => setMsg({ tone, text })
  const sayBad = seen => {
    forceGrant.current = null
    setForceAsk(false)
    setMsg(seen ? { tone: 'bad', ...seen } : { tone: 'bad', text: t('wa.invalid') })
  }
  const call = async fn => {
    if (pathNow.current !== shown) return null
    const ticket = actions.begin()
    if (!ticket) return null
    setBusy(true)
    const fresh = () => actions.current(ticket) && pathNow.current === shown
    try {
      const result = await fn(fresh)
      return fresh() ? result : null
    } catch (e) {
      if (fresh()) say('bad', errText(e))
      return null
    } finally {
      if (actions.finish(ticket)) setBusy(false)
    }
  }
  const parentOf = path => String(path || '').replace(/[\\/][^\\/]+$/, '')

  const pick = async () => {
    if (!actions.matches()) return
    const os = ctxRef?.os
    if (!os?.pickOpenPath) { say('bad', t('wa.noPicker')); return }
    const res = await call(async fresh => {
      let picked = null
      try {
        picked = await os.pickOpenPath({
          title: t('wa.pickTitle'), defaultPath: idFilePath(shown), filters: [
            { name: t('wa.pickFilter'), extensions: ['json', 'md'] },
            { name: t('wa.pickAny'), extensions: ['*'] }
          ]
        })
      } catch (e) { picked = null }
      if (!fresh()) return null
      return picked ? api.derive(picked) : { cancelled: true }
    })
    if (!actions.matches() || !res) return
    if (res.cancelled) { say('info', t('wa.pickCancelled')); return }
    if (res.ok) { changeDraft(res.root); say('ok', t('wa.derived', res.root)) }
    else sayBad(txReason(res.reason || res.error, res.reason_source, t))
  }

  const verify = async () => {
    if (!actions.matches()) return
    if (!shown) { say('bad', t('wa.invalid')); return }
    const res = await call(() => api.validate(shown))
    if (!actions.matches()) return
    if (res) setChecked({ path: shown, ok: Boolean(res.ok) })
    if (res?.ok) say('ok', t('wa.verified', res.pages ?? 0, res.id || '—'))
    else if (res) sayBad(txReason(res.reason || res.error, res.reason_source, t))
  }

  let saveUsed = false
  const reviewedForce = forceGrant.current
  const save = async (force = false) => {
    if (!actions.matches() || pathNow.current !== shown || saveUsed) return
    if (force && (forceGrant.current !== reviewedForce || forceGrant.current?.path !== shown
      || forceGrant.current?.scope !== auto.scope.key)) return
    if (!shown) { say('bad', t('wa.invalid')); return }
    saveUsed = true
    forceGrant.current = null
    const res = await call(() => api.save(shown, force))
    if (!actions.matches()) return
    if (res?.ok) {
      say('ok', t('wa.saved', res.project_root))
      setDraft('')
      setCands(null)
      setForceAsk(false)
      refreshAuto?.()
    } else if (res?.needs_force) {
      const question = txReason(res.reason, res.reason_source, t)
      forceGrant.current = { path: shown, scope: auto.scope.key }
      setForceAsk(true)
      setMsg({ tone: 'info', text: question ? question.text : t('wa.forceAsk'), ask: true })
    } else if (res) {
      sayBad(txReason(res.reason || res.error, res.reason_source, t))
    }
  }

  const showScan = (res, root, prefix) => {
    if (!actions.matches()) return
    if (!res) return
    if (res.ok === false) {
      sayBad(txReason(res.reason || res.error, res.reason_source, t))
      return
    }
    const found = (res.found || []).filter(c => normalize(c.root) !== normalize(current))
    setCands(found)
    const bits = []
    if (res.scanned) bits.push(t('wa.scanScanned', res.scanned))
    if (res.skipped) bits.push(t('wa.scanSkipped', res.skipped))
    if (res.truncated) bits.push(t('wa.scanTruncated'))
    const head = prefix ? [prefix] : []
    if (!found.length) {
      say('info', [...head, t('wa.noCandidates', res.root || root || '—'), ...bits].join(' · '))
    } else {
      say('info', [...head, ...(bits.length ? bits : [t('wa.candidates')])].join(' · '))
    }
  }

  const scanRootFrom = picked => {
    const folder = parentOf(picked)
    const name = folder.split(/[\\/]/).pop() || ''
    return name.startsWith('.') ? parentOf(folder) : folder
  }

  const scan = async (rootOverride, prefix) => {
    const root = rootOverride === undefined ? parentOf(shown) : rootOverride
    const res = await call(() => api.candidates(root))
    showScan(res, root, prefix)
  }

  const pickScanRoot = async () => {
    if (!actions.matches()) return
    const os = ctxRef?.os
    if (!os?.pickOpenPath) { say('bad', t('wa.noPicker')); return }
    const res = await call(async fresh => {
      let picked = null
      try { picked = await os.pickOpenPath({ title: t('wa.scanRootPick') }) }
      catch (e) { picked = null }
      if (!fresh()) return null
      if (!picked) return { cancelled: true }
      const folder = scanRootFrom(picked)
      const saved = await api.scanRoot(folder)
      if (!fresh()) return null
      if (!saved?.ok) return saved
      const found = await api.candidates(folder)
      return { ok: true, found, folder, prefix: t('wa.scanRootSaved', saved.scan_root) }
    })
    if (!actions.matches() || !res) return
    if (res.cancelled) say('info', t('wa.pickCancelled'))
    else if (res.ok) showScan(res.found, res.folder, res.prefix)
    else {
      sayBad(txReason(res.reason || res.error, res.reason_source, t))
    }
  }

  if (auto?.error && !info) return jsx(Failure, { t, text: t('wa.loadFailed'), detail: auto.error }, 'failed')
  if (!info) return jsx('div', { className: 'wa-body', children: jsx(Loading, {}, 'lw') }, 'loading')
  if (info.available === false) {
    return jsx(Failure, { text: info.error || t('wa.unavailable') }, 'unavailable')
  }

  const needle = filter.trim().toLowerCase()
  const visible = (cands || []).filter(c => !needle || String(c.root || '').toLowerCase().includes(needle))
  const question = msg?.raw && msg.raw !== msg.text ? msg.raw : null
  const head = !msg ? t('wa.helpResult')
    : (msg.tone === 'bad' ? t('wa.helpRefused')
      : (msg.tone === 'info' ? t('wa.helpNote') : t('wa.helpResult')))

  return jsxs('div', { className: 'wa-body wa-set', 'aria-busy': busy, children: [
    jsx(Stale, { error: auto?.error, t }, 'stale'),
    jsx(PanelMeta, { className: 'wa-kv', rows: [rootRow(t, current, verdict)] }, 'kv'),
    jsx(SetRow, { label: t('wa.setChangeTo'), note: forceAsk || msg ? null : t('wa.loud'), inline: true, value: jsx(Input, {
        'aria-label': t('wa.root'),
        className: 'wa-path-input',
        disabled: unread,
        onChange: e => changeDraft(e.target.value),
        placeholder: t('wa.placeholder'),
        size: 'sm',
        value: draft
      }, 'i'),
    actions: [
      draftVerdict == null ? null : Status({ text: draftVerdict ? t('wa.ok') : t('wa.invalid'),
        variant: draftVerdict ? 'success' : 'destructive', badgeKey: 'dv' }),
      jsx(Button, { disabled: busy || unread, onClick: pick, size: 'sm', variant: 'outline',
        children: t('wa.pick') }, 'pick'),
      jsx(Button, { disabled: busy || unread || !shown, onClick: verify, size: 'sm', variant: 'outline',
        children: t('wa.verify') }, 'verify'),
      jsx(Button, { disabled: busy || unread || !shown || !draft, onClick: () => save(false), size: 'sm',
        variant: 'default', children: t('wa.save') }, 'save')
    ] }, 'row'),
    jsx(SetRow, { label: t('wa.setFind'), note: t('wa.setFindNote'), value: null, actions: [
      jsx(Button, { disabled: busy || unread, onClick: () => scan(), size: 'sm', variant: 'outline',
        children: t('wa.scan') }, 'scan'),
      !shown ? jsx(Button, { disabled: busy || unread, onClick: pickScanRoot, size: 'sm', variant: 'outline',
        children: t('wa.scanRootPick') }, 'scanroot') : null
    ] }, 'find'),
    jsx('div', { 'aria-live': 'polite', className: 'wa-live', children: msg && !forceAsk
      ? jsxs('div', { className: 'wa-help', children: [
        jsx('div', { className: 'wa-help-title', children: head }, 'h'),
        jsx(Tip, { label: question, children: jsx('div', {
          'data-tone': msg.tone,
          className: 'wa-msg',
          children: (busy ? `${t('wa.working')} ` : '') + msg.text
        }, 'm') }, 'mt'),
        question
          ? jsx(Tip, { label: question, children: jsxs('div', {
            className: 'wa-raw',
            children: [
              jsxs('div', { className: 'wa-code-head', children: [
                jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, 'c'),
                Copy({ copyKey: 'b', text: msg.raw })
              ] }, 'ch'),
              jsx(PanelBlock, { className: 'wa-mono', children: msg.raw }, 'p')
            ]
          }, 'raw') }, 'rt')
          : null,
        msg.tone === 'bad' && question
          ? jsx(Button, { className: 'wa-help-act', disabled: busy, onClick: pick, size: 'sm',
            variant: 'outline', children: t('wa.pickAgain') }, 'act')
          : null
      ] }, 'msgs')
      : null }, 'live'),
    forceAsk
      ? jsxs('div', { className: 'wa-confirm', children: [
        jsx('span', { className: 'wa-confirm-text',
          children: (msg?.ask && msg.text) || t('wa.forceAsk') }, 'q'),
        jsxs('div', { className: 'wa-confirm-row', children: [
          jsx(Button, { className: 'wa-danger-fill', disabled: busy || unread, onClick: () => save(true),
            size: 'sm', variant: 'destructive', children: t('wa.forceYes') }, 'y'),
          jsx(Button, { disabled: busy, onClick: () => {
            if (actions.matches() && forceGrant.current === reviewedForce) {
              forceGrant.current = null; setForceAsk(false)
            }
          }, size: 'sm',
            variant: 'outline', children: t('wa.forceNo') }, 'n')
        ] }, 'r')
      ] }, 'force')
      : null,
    cands && cands.length
      ? jsxs('div', { className: 'wa-cands', children: [
        jsxs('div', { className: 'wa-cand-head', children: [
          jsx(PanelSectionLabel, { className: 'wa-sec-title', children: t('wa.candidates') }, 'h'),
          jsx(SearchField, {
            'aria-label': t('wa.filterPlaceholder'),
            containerClassName: 'desktop-input-chrome wa-filter',
            inputClassName: 'wa-filter-input',
            onChange: value => { if (actions.matches()) setFilter(value) },
            placeholder: t('wa.filterPlaceholder'),
            value: filter
          }, 'f')
        ] }, 'ch'),
        visible.length
          ? visible.map(c => jsx(Tip, {
            label: isCopy(c) ? t('wa.sameIdHint') : t('wa.candidateHint'),
            children: jsx(RowButton, {
              className: 'wa-cand',
              onClick: () => {
                if (!actions.matches()) return
                changeDraft(c.root, isCopy(c))
                say(isCopy(c) ? 'info' : 'ok',
                  isCopy(c) ? t('wa.sameIdHint') : t('wa.derived', c.root))
              },
              children: jsxs('span', { className: 'wa-cand-row', children: [
                jsx('span', { className: 'wa-mono wa-clip wa-cand-path', children: c.root }, 'r'),
                jsx(Badge, { className: 'wa-cand-pages', variant: 'muted',
                  children: t('wa.candPages', c.pages ?? 0) }, 'n'),
                isCopy(c) ? Status({ text: t('wa.sameId'), variant: 'warn', badgeKey: 'b' }) : null
              ] }, 'row')
            }, c.root)
          }, c.root))
          : jsx('div', { className: 'wa-empty', children: jsx(EmptyState, {
            description: t('wa.filterNoneHint'), title: t('wa.filterNone') }, 'e') }, 'none')
      ] }, 'cands')
      : null
  ] })
}

const engineHex = (text, size) => typeof text === 'string'
  && new RegExp(`^[a-f0-9]{${size}}$`).test(text)
const engineText = text => typeof text === 'string' && Boolean(text.trim())
const engineAbsolute = text => engineText(text) && (text.startsWith('/') || /^[a-zA-Z]:[\\/]/.test(text)
  || /^\\\\[^\\]+\\[^\\]+/.test(text))

function EngineInstall({ t, auto, onEngineState }) {
  const [status, setStatus] = useState(null)
  const [statusBusy, setStatusBusy] = useState(true)
  const [statusError, setStatusError] = useState('')
  const [chosen, setChosen] = useState(null)
  const [plan, setPlan] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [contextChanged, setContextChanged] = useState(false)
  const projectKey = JSON.stringify([auto?.data?.settings?.project_root || '',
    auto?.data?.settings?.project?.id || ''])
  const projectNow = useRef(projectKey)
  projectNow.current = projectKey
  const projectSeen = useRef(projectKey)
  const projectLoaded = Boolean(auto?.data)
  const projectSeenLoaded = useRef(projectLoaded)
  const automationReady = useRef(false)
  automationReady.current = !auto?.busy && !auto?.error
  const epoch = useRef(0)
  const alive = useRef(true)
  const pending = useRef(false)
  const planScope = useRef(null)
  const statusScope = useRef(null)
  const statusRequest = useRef(0)
  const lastReported = useRef({ key: '', state: null })
  const context = () => ({ cwd: host.state.cwd.get(), connectionId: host.state.connectionId.get(),
    profile: host.state.profile.get(), project: projectNow.current, epoch: epoch.current })
  const identityKnown = captured => captured
    && (captured.connectionId === null || typeof captured.connectionId === 'string')
    && (captured.profile === null || typeof captured.profile === 'string')
    && (captured.cwd === null || captured.cwd === '' || engineAbsolute(captured.cwd))
  const matches = captured => {
    const now = context()
    return alive.current && identityKnown(now) && identityKnown(captured) && now.connectionId === captured.connectionId
      && now.cwd === captured.cwd && now.profile === captured.profile
      && now.project === captured.project && now.epoch === captured.epoch
  }
  const invalidate = (switched, announce = true) => {
    epoch.current += 1
    pending.current = false
    planScope.current = null
    statusScope.current = null
    statusRequest.current += 1
    setStatus(null)
    setPlan(null)
    setChosen(null)
    setBusy(false)
    setMessage(announce ? t('wa.engineScopeChanged') : '')
    if (switched) setContextChanged(true)
  }
  const readStatus = async () => {
    if (pending.current) return
    statusScope.current = null
    planScope.current = null
    setPlan(null)
    setStatus(null)
    const ticket = ++statusRequest.current
    const captured = context()
    const current = () => matches(captured) && ticket === statusRequest.current
    if (!identityKnown(captured)) {
      setStatusError(t('wa.engineIdentityUnavailable')); setStatusBusy(false); return
    }
    setStatusBusy(true)
    setStatusError('')
    try {
      if (!current()) return
      const res = await ctxRef.rest('/engine/status') || {}
      if (!current()) return
      const valid = res.ok === true && engineHex(res.selected_revision, 40)
        && (res.current_revision === null || engineHex(res.current_revision, 40))
        && ['missing', 'prepared', 'applying', 'installed_paused', 'installed_with_existing_jobs',
          'recovery_required', 'unavailable', 'existing_unverified'].includes(res.state)
      statusScope.current = valid ? captured : null
      setStatus(valid ? res : null)
      if (!valid) setStatusError(t('wa.engineStatusFailed'))
      const reason = txReason(res.reason || res.error, res.reason_source, t)
      if (reason) setMessage(reason.text)
    } catch (e) {
      if (current()) { setStatus(null); setStatusError(errText(e)) }
    } finally { if (current()) setStatusBusy(false) }
  }
  const root = chosen === null ? (contextChanged ? '' : auto?.data?.settings?.project_root || '') : chosen
  const scopeKey = c => JSON.stringify([c.connectionId, c.cwd, c.profile, c.project])
  const confirmed = matches(statusScope.current) && status?.ok === true ? status.state : null
  if (confirmed) lastReported.current = { key: scopeKey(context()), state: confirmed }
  const inFlight = statusBusy || pending.current
  const reported = confirmed
    || (inFlight && lastReported.current.key === scopeKey(context()) ? lastReported.current.state : null)
  useEffect(() => { onEngineState?.(reported) }, [reported])
  const allowed = !auto?.busy && !auto?.error && !statusBusy && matches(statusScope.current) && status?.ok === true
    && ['missing', 'prepared', 'installed_paused', 'installed_with_existing_jobs', 'existing_unverified'].includes(status.state)
  const recoverable = !statusBusy && matches(statusScope.current) && !auto?.busy && !auto?.error && status?.ok === true
    && ['applying', 'recovery_required'].includes(status.state)
    && engineHex(status.install_id, 64) && engineHex(status.plan_digest, 64)
  const displayedStatusScope = statusScope.current
  const displayedContext = context()
  const identityReady = identityKnown(displayedContext)
  const displayedRequest = statusRequest.current
  const displayedReview = planScope.current
  const displayedMatches = () => matches(displayedContext) && statusRequest.current === displayedRequest
    && planScope.current === displayedReview
  const retryStatus = () => { if (!pending.current && displayedMatches()) return readStatus() }
  const reviewRecovery = async () => {
    if (!recoverable || pending.current || !automationReady.current || !displayedMatches() || !displayedStatusScope
      || statusScope.current !== displayedStatusScope || !matches(displayedStatusScope)) return
    const captured = displayedStatusScope
    statusScope.current = null
    pending.current = true
    planScope.current = null
    setPlan(null)
    setBusy(true)
    setMessage('')
    try {
      const res = await ctxRef.rest('/engine/recovery/prepare', { method: 'POST',
        body: { install_id: status.install_id } }) || {}
      if (!matches(captured)) return
      const valid = res.ok === true && res.state === 'recovery_prepared'
        && res.install_id === status.install_id && res.plan_digest === status.plan_digest
        && engineHex(res.revision, 40) && engineAbsolute(res.project_root)
        && engineAbsolute(res.requested_project_root) && engineText(res.project_id)
        && engineAbsolute(res.engine_dir) && engineAbsolute(res.audit_dir) && engineText(res.activation)
        && Array.isArray(res.jobs) && res.jobs.every(job => engineText(job.role)
          && engineText(job.name) && engineText(job.schedule))
        && engineHex(res.recovery_review_id, 64) && engineHex(res.recovery_review_digest, 64)
        && typeof res.review_expires_at === 'number' && Number.isFinite(res.review_expires_at)
        && res.review_expires_at <= Date.now() / 1000 + 300 && res.review_expires_at > Date.now() / 1000
      if (valid) { planScope.current = captured; setChosen(res.project_root); setPlan(res) }
      else setMessage(txReason(res.reason || res.error, res.reason_source, t)?.text
        || (res.ok === true && typeof res.review_expires_at === 'number' && res.review_expires_at <= Date.now() / 1000
          ? t('wa.engineRecoveryExpired') : res.ok === true ? t('wa.enginePlanInvalid') : t('wa.enginePrepareFailed')))
    } catch (e) { if (matches(captured)) setMessage(errText(e)) }
    finally { if (matches(captured)) {
      statusScope.current = { ...captured }
      pending.current = false
      setBusy(false)
    } }
  }
  useEffect(() => {
    alive.current = true
    const switched = () => { invalidate(true); readStatus() }
    const stopConnection = host.state.connectionId.listen(switched)
    const stopProfile = host.state.profile.listen(switched)
    const stopCwd = host.state.cwd.listen(switched)
    readStatus()
    return () => { alive.current = false; epoch.current += 1; stopConnection(); stopProfile(); stopCwd() }
  }, [])
  useLayoutEffect(() => {
    if (projectSeen.current !== projectKey) {
      const announce = projectSeenLoaded.current
      projectSeen.current = projectKey
      invalidate(false, announce)
      readStatus()
    }
  }, [projectKey])
  useLayoutEffect(() => { if (projectLoaded) projectSeenLoaded.current = true }, [projectLoaded])
  const pick = async () => {
    if (pending.current || !displayedMatches()) return
    if (!ctxRef?.os?.pickOpenPath) { setMessage(t('wa.noPicker')); return }
    const captured = displayedContext
    pending.current = true
    setBusy(true)
    try {
      const selected = await ctxRef.os.pickOpenPath({ title: t('wa.enginePickTitle'), defaultPath: root })
      if (!matches(captured)) return
      if (!selected) { setMessage(t('wa.pickCancelled')); return }
      const split = Math.max(String(selected).lastIndexOf('/'), String(selected).lastIndexOf('\\'))
      const folder = String(selected).slice(0, split === 0 || split === 2 && selected[1] === ':' ? split + 1 : split)
      if (!engineAbsolute(folder)) { setMessage(t('wa.engineAbsolute')); return }
      invalidate(false)
      setChosen(folder)
      setMessage('')
      readStatus()
    } catch (e) { if (matches(captured)) setMessage(errText(e)) }
    finally { if (matches(captured)) { pending.current = false; setBusy(false) } }
  }
  const prepare = async () => {
    if (!engineAbsolute(root) || pending.current || !allowed || !automationReady.current
      || !displayedMatches() || !displayedStatusScope
      || statusScope.current !== displayedStatusScope || !matches(displayedStatusScope)) return
    const captured = displayedStatusScope
    pending.current = true
    planScope.current = null
    setPlan(null)
    setBusy(true)
    setMessage('')
    try {
      const res = await ctxRef.rest('/engine/prepare', { method: 'POST', body: { project_root: root } }) || {}
      if (!matches(captured)) return
      const valid = res?.ok === true && res.state === 'prepared' && engineHex(res.install_id, 64)
        && engineHex(res.plan_digest, 64) && res.revision === status.selected_revision
        && (res.requested_project_root || res.project_root) === root && engineAbsolute(res.project_root)
        && engineText(res.project_id) && engineAbsolute(res.engine_dir)
        && engineAbsolute(res.audit_dir) && engineText(res.activation) && Array.isArray(res.jobs)
        && res.jobs.every(job => engineText(job.role) && engineText(job.name) && engineText(job.schedule))
      if (valid) { planScope.current = { ...captured }; setPlan(res) }
      else {
        if (res?.state === 'recovery_required') { setStatus(res); setPlan(null) }
        setMessage(txReason(res.reason || res.error, res.reason_source, t)?.text
          || (res?.ok === true ? t('wa.enginePlanInvalid') : t('wa.enginePrepareFailed')))
      }
    } catch (e) { if (matches(captured)) setMessage(errText(e)) }
    finally { if (matches(captured)) { pending.current = false; setBusy(false) } }
  }
  const expireRecovery = () => {
    planScope.current = null
    setPlan(null)
    setMessage(t('wa.engineRecoveryExpired'))
  }
  useEffect(() => {
    if (plan?.state !== 'recovery_prepared') return
    const captured = planScope.current
    let timer
    const tick = () => {
      if (!captured || planScope.current !== captured || !matches(captured)) return
      const remaining = plan.review_expires_at * 1000 - Date.now()
      if (remaining <= 0) expireRecovery()
      else timer = setTimeout(tick, Math.min(remaining, 2147483647))
    }
    tick()
    return () => clearTimeout(timer)
  }, [plan])
  const displayedScope = planScope.current
  const resumeRecovery = async () => {
    if (!plan || plan.state !== 'recovery_prepared' || pending.current || !recoverable || !automationReady.current
      || !displayedScope || planScope.current !== displayedScope) return
    const captured = displayedScope
    if (!matches(captured)) { invalidate(true); return }
    if (plan.review_expires_at <= Date.now() / 1000) { expireRecovery(); return }
    statusScope.current = null
    pending.current = true
    planScope.current = null
    setBusy(true)
    setMessage('')
    try {
      const res = await ctxRef.rest('/engine/recovery/apply', { method: 'POST', body: {
        install_id: plan.install_id, plan_digest: plan.plan_digest,
        recovery_review_id: plan.recovery_review_id, recovery_review_digest: plan.recovery_review_digest,
        confirm: true } }) || {}
      if (!matches(captured)) return
      if (res.ok === true && ['installed_paused', 'installed_with_existing_jobs'].includes(res.state)
        && res.activation_required === true && res.install_id === plan.install_id && res.revision === plan.revision) {
        setStatus({ ...res, selected_revision: status.selected_revision, current_revision: res.revision })
        setPlan(null)
      } else setMessage(txReason(res.reason || res.error, res.reason_source, t)?.text || t('wa.engineApplyFailed'))
    } catch (e) { if (matches(captured)) setMessage(errText(e)) }
    finally { if (matches(captured)) {
      statusScope.current = { ...captured }
      pending.current = false
      setBusy(false)
      setPlan(null)
    } }
  }
  const apply = async () => {
    if (!plan || pending.current || !allowed || !automationReady.current || planScope.current !== displayedScope) return
    const captured = displayedScope
    if (!matches(captured)) { invalidate(true); return }
    pending.current = true
    setBusy(true)
    setMessage('')
    try {
      const res = await ctxRef.rest('/engine/apply', { method: 'POST', body: {
        install_id: plan.install_id, plan_digest: plan.plan_digest, confirm: true } }) || {}
      if (!matches(captured)) return
      if (res?.ok === true && ['installed_paused', 'installed_with_existing_jobs'].includes(res.state)
        && res.activation_required === true
        && res.install_id === plan.install_id && res.revision === plan.revision) {
        setStatus({ ...res, selected_revision: plan.revision, current_revision: res.revision })
        planScope.current = null
        setPlan(null)
      } else {
        if (res?.state === 'recovery_required') { planScope.current = null; setStatus(res); setPlan(null) }
        setMessage(txReason(res.reason || res.error, res.reason_source, t)?.text || t('wa.engineApplyFailed'))
      }
    } catch (e) { if (matches(captured)) setMessage(errText(e)) }
    finally { if (matches(captured)) { pending.current = false; setBusy(false) } }
  }
  const stateText = statusError ? t('wa.engineStatusFailed') : status?.state === 'missing' ? t('wa.engineMissing')
    : status?.state === 'existing_unverified' ? t('wa.engineExistingUnverified')
    : status?.state === 'installed_paused' ? t('wa.engineInstalled')
    : status?.state === 'installed_with_existing_jobs' ? t('wa.engineExisting')
    : status?.state === 'prepared' ? t('wa.enginePrepared')
    : status?.state === 'applying' ? t('wa.engineApplying')
    : status?.state === 'recovery_required' ? t('wa.engineRecovery')
    : status?.state === 'unavailable' ? t('wa.engineUnavailable') : t('wa.working')
  const installed = ['installed_paused', 'installed_with_existing_jobs'].includes(status?.state)
  const ships = installed ? engineUpdate(status) : null
  return jsxs('div', { className: 'wa-body wa-engine', children: [
    jsx(SetRow, { label: t('wa.setEngine'), note: jsxs('span', { className: 'wa-engine-notes', children: [
      jsx('span', { children: stateText }, 'state'),
      installed ? jsx('span', { children: status.state === 'installed_paused' ? t('wa.engineActivate')
        : t('wa.engineExistingNote') }, 'activation') : null,
      ships ? jsx('span', { children: t('wa.engineShips', ships.selected) }, 'ships') : null
    ] }), value: installed ? jsxs('span', { className: 'wa-engine-rev', children: [
      jsx(Tip, { label: status.current_revision, children: jsx('span', { className: 'wa-mono',
        children: String(status.current_revision || '').slice(0, 7) }) }, 'revision'),
      ships ? jsx('span', { className: 'wa-engine-next', children: `→ ${String(ships.selected).slice(0, 7)}` }, 'next') : null
    ] }) : null, actions: [
      recoverable ? jsx(Button, { size: 'sm', variant: 'outline', disabled: busy || statusBusy,
        onClick: reviewRecovery, children: t('wa.engineRecoveryReview') }, 'review-recovery') : null,
      jsx(Button, { size: 'sm', variant: 'outline', disabled: busy || !engineAbsolute(root) || !allowed,
        onClick: prepare, children: status?.current_revision || status?.state === 'existing_unverified'
          ? t('wa.engineUpdate') : t('wa.enginePreview') }, 'preview'),
      statusError || ['applying', 'recovery_required', 'unavailable'].includes(status?.state)
        ? jsx(Button, { size: 'sm', variant: 'outline', disabled: busy || statusBusy,
          onClick: retryStatus, children: t('wa.engineRetryStatus') }, 'retry') : null
    ] }, 'state'),
    jsx(SetRow, { label: t('wa.setEngineInto'), note: t('wa.enginePickHint'), inline: true,
      value: jsx(Input, { 'aria-label': t('wa.engineRootLabel'), className: 'wa-mono wa-path-input',
        disabled: busy || !identityReady, value: root, placeholder: t('wa.placeholder'), size: 'sm', onChange: event => {
          if (!displayedMatches()) return
          invalidate(false); setChosen(event.target.value); setMessage(''); readStatus()
        } }, 'root'),
      actions: [jsx(Button, { size: 'sm', variant: 'outline', disabled: busy || !identityReady, onClick: pick,
        children: t('wa.engineChoose') }, 'pick')] }, 'into'),
    plan ? jsxs('div', { className: 'wa-engine-plan', role: 'region', tabIndex: 0,
      'aria-label': plan.state === 'recovery_prepared' ? t('wa.engineRecoveryLabel') : t('wa.enginePlanLabel'), children: [
      plan.state === 'recovery_prepared' ? jsxs('div', { children: [
        jsx('p', { children: t('wa.engineRecoveryOriginal') }, 'original'),
        jsx('p', { children: t('wa.engineRecoveryFresh') }, 'fresh'),
        jsx('p', { children: t('wa.engineRecoveryAdmin') }, 'admin'),
        jsx('p', { children: `${t('wa.engineRecoveryExpiry')}: ${new Date(plan.review_expires_at * 1000).toISOString()}` }, 'expiry')
      ] }, 'recovery-review') : null,
      jsx(PanelMeta, { className: 'wa-kv', rows: [
        { label: plan.state === 'recovery_prepared' ? t('wa.engineRecoveryRevision') : t('wa.engineRevision'),
          value: plan.revision },
        { label: t('wa.root'), value: plan.project_root },
        ...(plan.state === 'recovery_prepared' && plan.requested_project_root !== plan.project_root
          ? [{ label: t('wa.engineRecoveryRequestedRoot'), value: plan.requested_project_root }] : []),
        { label: t('wa.engineProjectId'), value: plan.project_id },
        { label: t('wa.engineCodeDir'), value: plan.engine_dir },
        { label: t('wa.engineDataDir'), value: plan.audit_dir },
        { label: plan.state === 'recovery_prepared' ? t('wa.engineRecoveryInstallId') : t('wa.engineInstallId'),
          value: plan.install_id },
        { label: plan.state === 'recovery_prepared' ? t('wa.engineRecoveryPlanDigest') : t('wa.enginePlanDigest'),
          value: plan.plan_digest }
      ] }, 'fields'),
      ...(plan.jobs || []).map(job => jsx('div', { className: 'wa-engine-job wa-mono',
        children: `${job.role} · ${job.name} · ${job.schedule}${{ adopt_existing: ` · ${t('wa.engineJobAdopt')}`,
          adopt_paused: ` · ${t('wa.engineJobAdoptPaused')}`, keep_existing: ` · ${t('wa.engineJobKeep')}`,
          refresh_prompt: ` · ${t('wa.engineJobRefreshPrompt')}`, refresh_interpreter: ` · ${t('wa.engineJobRefreshInterpreter')}`,
          create_paused: ` · ${t('wa.engineJobNew')}` }[job.disposition] || ''}` }, job.role)),
      jsx('p', { children: plan.activation }, 'activation'),
      jsx('p', { children: t('wa.engineConsequence') }, 'consequence'),
      jsxs('div', { className: 'wa-inline', children: [
        plan.state === 'recovery_prepared'
          ? jsx(Button, { size: 'sm', disabled: busy || !recoverable || !displayedScope,
            onClick: resumeRecovery, children: t('wa.engineRecoveryResume') }, 'confirm')
          : jsx(Button, { size: 'sm', disabled: busy || !allowed, onClick: apply, children: t('wa.engineConfirm') }, 'confirm'),
        jsx(Button, { size: 'sm', variant: 'outline', disabled: busy, onClick: () => {
          if (pending.current || !matches(displayedScope) || planScope.current !== displayedScope) return
          planScope.current = null; setPlan(null); setMessage('')
        }, children: t('wa.engineDiscard') }, 'discard')
      ] }, 'confirm-row')
    ] }, 'plan') : null,
    busy || statusBusy ? jsx(Loading, {}, 'pending') : null,
    statusError ? jsx(ErrorState, { description: statusError }, 'status-error') : null,
    jsx('div', { role: 'status', 'aria-live': 'polite', children: busy ? t('wa.working') : message }, 'message')
  ] })
}

function InstallCard({ t, auto, onEngineState }) {
  return jsxs('div', { className: 'wa-body', children: [jsx(EngineInstall, { t, auto, onEngineState }, 'engine'),
    auto?.data?.available || auto?.error && !auto?.data
      ? jsx(InstallationFilesCard, { t, auto }, 'files') : null] })
}

function InstallationFilesCard({ t, auto }) {
  const info = auto?.data || null
  if (auto?.error && !info) return jsx(Failure, { t, text: t('wa.loadFailed'), detail: auto.error }, 'failed')
  if (!info) return jsx('div', { className: 'wa-body', children: jsx(Loading, {}, 'lw') }, 'loading')
  const settings = info?.settings || null
  const scripts = info?.scripts || {}
  const ok = Object.values(scripts).filter(Boolean).length
  const total = Object.keys(scripts).length
  const missing = Object.keys(scripts).filter(name => !scripts[name])
  const cell = (text, bad) => bad
    ? jsx('span', { className: 'wa-clip wa-bad', children: text })
    : jsx('span', { className: 'wa-clip', children: text })
  const rows = [
    { label: t('wa.settingsFile'), value: cell(settings?.settings_path || '—') },
    { label: t('wa.auditDir'), value: cell(info?.audit_dir || '—') },
    {
      label: t('wa.scripts'),
      value: total
        ? jsx(Tip, { label: missing.length
          ? `${t('wa.scriptsMissing')}: ${missing.join(', ')}`
          : t('wa.scriptsAll'), children: cell(t('wa.ofTotal', ok, total), ok !== total) }, 's')
        : cell('—')
    }
  ]
  return jsxs('div', { className: 'wa-body', children: [
    jsx(Stale, { error: auto?.error, t }, 'stale'),
    jsx(PanelMeta, { className: 'wa-kv', rows }, 'kv')
  ] })
}

const SCHED_MODES = ['minutes', 'hourly', 'daily', 'weekly', 'monthly', 'custom']
const SCHED_MODE_LABEL = {
  minutes: 'wa.modeMinutes', hourly: 'wa.modeHourly', daily: 'wa.modeDaily', weekly: 'wa.modeWeekly',
  monthly: 'wa.modeMonthly', custom: 'wa.modeCustom'
}
const EVERY_MINUTES = ['5', '10', '15', '30']
const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0]
const PREVIEW_DELAY_MS = 250
const two = n => String(n).padStart(2, '0')
const intIn = (text, lo, hi) => (/^\d{1,2}$/.test(String(text)) && Number(text) >= lo && Number(text) <= hi
  ? Number(text) : null)
const clockOf = (hh, mm) => `${two(hh)}:${two(mm)}`

function parseClock(text) {
  const m = String(text || '').match(/^(\d{1,2}):(\d{2})$/)
  if (!m) return null
  const hh = Number(m[1])
  const mm = Number(m[2])
  return hh <= 23 && mm <= 59 ? { hh, mm } : null
}

function parseDows(field) {
  const out = new Set()
  for (const part of String(field).split(',')) {
    const range = part.match(/^(\d)(?:-(\d))?$/)
    if (!range) return null
    const lo = Number(range[1])
    const hi = range[2] === undefined ? lo : Number(range[2])
    if (lo > 7 || hi > 7 || hi < lo) return null
    for (let d = lo; d <= hi; d += 1) out.add(d % 7)
  }
  return out.size ? DOW_ORDER.filter(d => out.has(d)) : null
}

function cronToSched(expr) {
  const text = String(expr || '').trim()
  const base = { mode: 'custom', every: '15', minute: '0', time: '09:00', days: [1], dom: '1', raw: text }
  const parts = text.split(/\s+/)
  if (parts.length !== 5) return base
  const [mi, hr, dom, mon, dow] = parts
  if (mon !== '*') return base
  const minute = intIn(mi, 0, 59)
  const hour = intIn(hr, 0, 23)
  const everyMin = mi.match(/^(?:\*|0)\/(\d{1,2})$/)
  if (everyMin && EVERY_MINUTES.includes(String(Number(everyMin[1]))) && hr === '*' && dom === '*' && dow === '*') {
    return { ...base, mode: 'minutes', every: String(Number(everyMin[1])) }
  }
  if (minute === null) return base
  if (hr === '*' && dom === '*' && dow === '*') return { ...base, mode: 'hourly', minute: String(minute) }
  if (hour === null) return base
  const time = clockOf(hour, minute)
  if (dom === '*' && dow === '*') return { ...base, mode: 'daily', time }
  if (dom === '*') {
    const days = parseDows(dow)
    return days ? { ...base, mode: 'weekly', time, days } : base
  }
  const day = intIn(dom, 1, 31)
  if (day !== null && dow === '*') return { ...base, mode: 'monthly', time, dom: String(day) }
  return base
}

function dowField(days) {
  const out = []
  for (let i = 0; i < days.length; i += 1) {
    let j = i
    while (j + 1 < days.length && days[j + 1] === days[j] + 1) j += 1
    out.push(j - i >= 2 ? `${days[i]}-${days[j]}` : days.slice(i, j + 1).join(','))
    i = j
  }
  return out.join(',')
}

const schedKey = s => JSON.stringify([s.mode, s.every, String(s.minute), s.time, [...(s.days || [])].sort(),
  String(s.dom), String(s.raw || '').trim()])

function schedToCron(s) {
  const clock = parseClock(s.time)
  if (s.mode === 'minutes') return EVERY_MINUTES.includes(String(s.every)) ? `*/${s.every} * * * *` : ''
  if (s.mode === 'hourly') {
    const minute = intIn(s.minute, 0, 59)
    return minute === null ? '' : `${minute} * * * *`
  }
  if (s.mode === 'custom') return String(s.raw || '').trim().split(/\s+/).join(' ')
  if (!clock) return ''
  const head = `${clock.mm} ${clock.hh}`
  if (s.mode === 'daily') return `${head} * * *`
  if (s.mode === 'weekly') {
    const days = [0, 1, 2, 3, 4, 5, 6].filter(d => (s.days || []).includes(d))
    if (!days.length) return ''
    return days.length === 7 ? `${head} * * *` : `${head} * * ${dowField(days)}`
  }
  if (s.mode === 'monthly') {
    const day = intIn(s.dom, 1, 31)
    return day === null ? '' : `${head} ${day} * *`
  }
  return ''
}

function schedHuman(t, expr) {
  const s = cronToSched(expr)
  if (s.mode === 'custom') return t('wa.schCustom')
  if (s.mode === 'minutes') return t('wa.schEveryMin', s.every)
  if (s.mode === 'hourly') return s.minute === '0' ? t('wa.schHourTop') : t('wa.schHourAt', two(s.minute))
  if (s.mode === 'daily') return t('wa.schDaily', s.time)
  if (s.mode === 'monthly') return t('wa.schMonthly', s.dom, s.time)
  const key = s.days.join(',')
  if (key === '1,2,3,4,5') return t('wa.schWeekdays', s.time)
  if (key === '6,0') return t('wa.schWeekends', s.time)
  const names = t('wa.dayPlural').split(' ')
  return t('wa.schWeekly', s.days.map(d => names[DOW_ORDER.indexOf(d)]), s.time)
}

const ISO_STAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/

function isoParts(iso) {
  const m = String(iso || '').match(ISO_STAMP)
  const at = m ? Date.parse(String(iso)) : NaN
  if (!m || Number.isNaN(at)) return null
  const sign = m[6] && m[6].startsWith('-') ? -1 : 1
  const off = !m[6] ? -new Date(at).getTimezoneOffset()
    : (m[6] === 'Z' ? 0 : sign * (Number(m[6].slice(1, 3)) * 60 + Number(m[6].slice(4, 6))))
  return { y: Number(m[1]), mo: Number(m[2]), d: Number(m[3]), time: `${m[4]}:${m[5]}`, off, at }
}

function whenText(t, iso, now = Date.now()) {
  const p = isoParts(iso)
  if (!p) return String(iso || '—')
  const day = Date.UTC(p.y, p.mo - 1, p.d) / 86400000
  const there = new Date(now + p.off * 60000)
  const today = Date.UTC(there.getUTCFullYear(), there.getUTCMonth(), there.getUTCDate()) / 86400000
  if (day === today) return t('wa.dayToday', p.time)
  if (day === today + 1) return t('wa.dayTomorrow', p.time)
  if (day === today - 1) return t('wa.dayYesterday', p.time)
  const names = t('wa.dayShort').split(' ')
  const dow = (new Date(day * 86400000).getUTCDay() + 6) % 7
  return t('wa.dayOther', names[dow], two(p.d), two(p.mo), p.time)
}

function spanParts(t, seconds) {
  const mins = Math.abs(seconds) / 60
  if (mins < 60) return [Math.max(1, Math.round(mins)), t('wa.unitMin')]
  if (mins < 48 * 60) return [Math.round(mins / 60), t('wa.unitHour')]
  return [Math.round(mins / 1440), t('wa.unitDay')]
}

const COUNT_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
const countWord = n => COUNT_WORDS[n] || String(n)

function relText(t, iso, now = Date.now()) {
  const p = isoParts(iso)
  if (!p) return ''
  const diff = (p.at - now) / 1000
  if (Math.abs(diff) < 60) return t('wa.relNow')
  const [n, unit] = spanParts(t, diff)
  return diff > 0 ? t('wa.relIn', n, unit) : t('wa.relAgo', n, unit)
}

function runStamp(t, iso) {
  const rel = relText(t, iso)
  return rel ? `${whenText(t, iso)} · ${rel}` : whenText(t, iso)
}

function lastRunBadge(t, status) {
  if (!status) return null
  if (status === 'ok') return Status({ text: t('wa.runOk'), variant: 'success', badgeKey: 'r' })
  if (status === 'delivery_failed') return Status({ text: t('wa.runDeliveryFailed'), variant: 'warn', badgeKey: 'r' })
  return Status({ text: t('wa.runFailed'), variant: 'destructive', badgeKey: 'r' })
}

function dispatchBadge(t, dispatch) {
  if (!dispatch || !['late', 'missed'].includes(dispatch.flag)) return null
  const [n, unit] = spanParts(t, Number(dispatch.lateness_seconds) || 0)
  const late = t('wa.span', n, unit)
  const due = dispatch.scheduled_at ? whenText(t, dispatch.scheduled_at) : '—'
  const started = dispatch.dispatched_at ? whenText(t, dispatch.dispatched_at) : '—'
  const missed = dispatch.flag === 'missed'
  return jsx(Tip, {
    label: missed ? t('wa.runMissedTip', due, started, late) : t('wa.runLateTip', due, started, late),
    children: jsx('span', { className: 'wa-job-flag', 'data-flag': dispatch.flag, tabIndex: 0,
      children: Status({ text: missed ? t('wa.runMissed') : t('wa.runLate'), variant: missed ? 'destructive' : 'warn',
        badgeKey: 'f' }) }, 'f')
  }, 'flag')
}

function JobRunLine({ t, role }) {
  const paused = role.state === 'paused'
  const next = paused ? t('wa.runPaused') : (role.next_run_at ? runStamp(t, role.next_run_at) : '—')
  const last = role.last_run_at ? runStamp(t, role.last_run_at) : t('wa.runNever')
  return jsxs('span', { className: 'wa-job-runs', children: [
    jsxs('span', { className: 'wa-job-run', 'data-run': 'next', children: [
      jsx('span', { className: 'wa-job-runlabel', children: t('wa.runNext') }, 'l'),
      jsx('span', { className: 'wa-job-runval', children: next }, 'v')
    ] }, 'next'),
    jsxs('span', { className: 'wa-job-run', 'data-run': 'last', children: [
      jsx('span', { className: 'wa-job-runlabel', children: t('wa.runLast') }, 'l'),
      jsx('span', { className: 'wa-job-runval', children: last }, 'v'),
      lastRunBadge(t, role.last_status)
    ] }, 'last'),
    dispatchBadge(t, role.dispatch)
  ] }, 'runs')
}

function SchedField({ label, children, fieldKey }) {
  return jsxs('div', { className: 'wa-sched-field', children: [
    jsx('span', { className: 'wa-sched-lab', children: label }, 'l'),
    jsx('div', { className: 'wa-sched-ctl', children }, 'c')
  ] }, fieldKey)
}

function ScheduleEditor({ t, role, zone, busy, onSave, onCancel, scopeMatches }) {
  const current = String(role.schedule || role.planned_schedule || '').trim()
  const [initial] = useState(() => cronToSched(current))
  const [model, setModel] = useState(initial)
  const [preview, setPreview] = useState(null)
  const kept = Boolean(current) && initial.mode === 'custom'
  const expr = schedKey(model) === schedKey(initial) ? current : schedToCron(model)
  const patch = next => setModel(prev => ({ ...prev, ...next }))
  const pickMode = mode => setModel(prev => ({ ...prev, mode,
    raw: mode === 'custom' && prev.mode !== 'custom' ? (schedToCron(prev) || prev.raw) : prev.raw }))
  useEffect(() => {
    if (!expr) {
      setPreview(null)
      return undefined
    }
    let live = true
    setPreview({ expr, pending: true })
    const id = setTimeout(async () => {
      try {
        if (!live || !scopeMatches?.()) return
        const res = await api.jobPreview(expr)
        if (live && scopeMatches?.()) setPreview({ ...(res || {}), expr, pending: false })
      } catch (e) {
        if (live && scopeMatches?.()) setPreview({ expr, pending: false, ok: false, error: errText(e) })
      }
    }, PREVIEW_DELAY_MS)
    return () => { live = false; clearTimeout(id) }
  }, [expr])
  const shown = preview && preview.expr === expr && !preview.pending ? preview : null
  const refused = shown && shown.ok === false ? txReason(shown.reason || shown.error, shown.reason_source, t) : null
  const runs = shown && shown.ok ? (shown.next_runs || []) : []
  const zoneInfo = shown?.timezone || zone
  const timeField = jsx(Input, {
    'aria-label': t('wa.schAt'),
    className: 'wa-sched-time',
    onChange: e => patch({ time: e.target.value }),
    size: 'sm',
    step: 60,
    type: 'time',
    value: model.time
  }, 'time')
  const fields = []
  if (model.mode === 'minutes') {
    fields.push(SchedField({ fieldKey: 'every', label: t('wa.schEvery'), children: jsx(SegmentedControl, {
      'aria-label': t('wa.schEvery'),
      className: 'wa-sched-every',
      onChange: every => patch({ every }),
      options: EVERY_MINUTES.map(n => ({ id: n, label: t('wa.schMinUnit', n) })),
      value: model.every
    }, 'e') }))
  }
  if (model.mode === 'hourly') {
    fields.push(SchedField({ fieldKey: 'minute', label: t('wa.schAtMinute'), children: jsx(Input, {
      'aria-label': t('wa.schAtMinute'),
      className: 'wa-sched-num',
      max: 59,
      min: 0,
      onChange: e => patch({ minute: e.target.value }),
      size: 'sm',
      type: 'number',
      value: model.minute
    }, 'm') }))
  }
  if (model.mode === 'weekly') {
    const names = t('wa.dayShort').split(' ')
    fields.push(SchedField({ fieldKey: 'days', label: t('wa.schOnDays'), children: DOW_ORDER.map((d, i) => {
      const on = model.days.includes(d)
      return jsx(Button, {
        'aria-pressed': on,
        className: 'wa-day',
        onClick: () => patch({ days: on ? model.days.filter(x => x !== d) : [...model.days, d] }),
        size: 'sm',
        variant: 'outline',
        children: names[i]
      }, String(d))
    }) }))
  }
  if (model.mode === 'monthly') {
    fields.push(SchedField({ fieldKey: 'dom', label: t('wa.schOnDay'), children: jsx(Input, {
      'aria-label': t('wa.schOnDay'),
      className: 'wa-sched-num',
      max: 31,
      min: 1,
      onChange: e => patch({ dom: e.target.value }),
      size: 'sm',
      type: 'number',
      value: model.dom
    }, 'd') }))
  }
  if (['daily', 'weekly', 'monthly'].includes(model.mode)) {
    fields.push(SchedField({ fieldKey: 'time', label: t('wa.schAt'), children: timeField }))
  }
  if (model.mode === 'custom') {
    fields.push(SchedField({ fieldKey: 'raw', label: t('wa.schCron'), children: jsx(Input, {
      'aria-label': t('wa.schCron'),
      className: 'wa-sched-input',
      onChange: e => patch({ raw: e.target.value }),
      placeholder: '0 9 * * *',
      size: 'sm',
      value: model.raw
    }, 'r') }))
  }
  const notes = []
  if (model.mode === 'custom') {
    notes.push(kept && model.raw.trim() === current ? t('wa.schKeptNote') : t('wa.schCustomNote'))
  }
  if (model.mode === 'weekly' && !model.days.length) notes.push(t('wa.schNoDay'))
  if (model.mode === 'monthly' && Number(model.dom) > 28) notes.push(t('wa.schShortMonth'))
  return jsxs('div', { className: 'wa-confirm wa-job-confirm wa-sched', 'data-mode': model.mode, children: [
    jsx('span', { className: 'wa-confirm-text', children: t('wa.jobScheduleHint') }, 'q'),
    SchedField({ fieldKey: 'freq', label: t('wa.schFreq'), children: jsx(SegmentedControl, {
      'aria-label': t('wa.schFreq'),
      className: 'wa-sched-freq',
      onChange: pickMode,
      options: SCHED_MODES.map(id => ({ id, label: t(SCHED_MODE_LABEL[id]) })),
      value: model.mode
    }, 'f') }),
    ...fields,
    ...notes.map((text, i) => jsx('span', { className: 'wa-sched-note', children: text }, `n${i}`)),
    jsxs('div', { 'aria-live': 'polite', className: 'wa-sched-preview', children: [
      jsxs('span', { className: 'wa-sched-head', children: [
        jsx('span', { className: 'wa-label', children: t('wa.schPreview') }, 'l'),
        jsx('span', { className: 'wa-sched-human', children: expr ? schedHuman(t, expr) : '—' }, 'h'),
        expr ? jsx('span', { className: 'wa-mono wa-sched-expr', children: expr }, 'e') : null
      ] }, 'head'),
      refused
        ? jsxs('span', { className: 'wa-sched-runs wa-bad', 'data-tone': 'bad', children: [
          jsx('span', { children: t('wa.schPreviewRefused') }, 'a'),
          jsx('span', { className: 'wa-sched-why', children: refused.text }, 'b')
        ] }, 'bad')
        : jsx('span', { className: 'wa-sched-runs', children: !expr ? '—'
          : (!shown ? t('wa.schChecking') : `${t('wa.schNextRuns')}: ${runs.map(iso => whenText(t, iso)).join(' · ')
            || '—'}`) }, 'runs'),
      zoneInfo?.offset
        ? jsx('span', { className: 'wa-sched-zone', children: t('wa.schZone', zoneInfo.name || '', zoneInfo.offset) },
          'z')
        : null
    ] }, 'preview'),
    jsxs('div', { className: 'wa-sched-acts', children: [
      jsx(Button, { disabled: busy, onClick: onCancel, size: 'sm', variant: 'outline',
        children: t('wa.jobCancel') }, 'c'),
      jsx(Button, {
        className: 'wa-sched-save',
        disabled: busy || !expr || expr === current,
        onClick: () => onSave(expr),
        size: 'sm',
        variant: 'outline',
        children: t('wa.jobScheduleSave')
      }, 's')
    ] }, 'acts')
  ] }, 'sched')
}

function JobsCard({ t, jobs, auto, onInstall, only }) {
  const data = jobs?.data || null
  const mutationAvailable = data?.mutation_available === true
  const mutationNow = useRef(false)
  mutationNow.current = mutationAvailable
  const [armed, setArmed] = useState(null)
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)
  const [edit, setEdit] = useState(null)
  const armedNow = useRef(null)
  const editNow = useRef(null)
  const reviewedEdit = editNow.current
  const rowsKey = JSON.stringify((data?.roles || []).map(row => [row.role, row.id || null]))
  const rowsEpoch = useRef({ key: rowsKey, epoch: 0 })
  if (rowsEpoch.current.key !== rowsKey) rowsEpoch.current = { key: rowsKey, epoch: rowsEpoch.current.epoch + 1 }
  const rowEpoch = rowsEpoch.current.epoch
  const rowsNow = useRef(null)
  const rowFacts = new Map((data?.roles || []).map(row => [row.role,
    JSON.stringify([row.id || null, Boolean(row.live), row.state, row.schedule])]))
  rowsNow.current = rowFacts
  const rowMatches = role => rowEpoch === rowsEpoch.current.epoch
    && rowFacts.has(role) && rowsNow.current?.get(role) === rowFacts.get(role)
  const actions = usePanelActions([auto?.scope, jobs?.scope], () => {
    armedNow.current = null; editNow.current = null
    setArmed(null); setBusy(null); setNote(null); setEdit(null)
  })
  useLayoutEffect(() => {
    actions.cancel(); setBusy(null)
    armedNow.current = null; editNow.current = null; setArmed(null); setEdit(null)
  }, [rowsKey])
  const ready = () => actions.matches() && auto?.scope?.project === jobs?.scope?.project
  const actionable = () => mutationAvailable && mutationNow.current && ready()
    && auto?.scope?.fresh() && jobs?.scope?.fresh()
  useEffect(() => {
    if (auto?.scope?.matches() && jobs?.scope && auto.scope.project !== jobs.scope.project) jobs.refresh?.()
  }, [auto?.scope?.key, jobs?.scope?.key])
  const used = new Set()
  const begin = (role, action) => {
    const key = `${role}:${action}`
    if (!actionable() || !rowMatches(role) || used.has(key)) return null
    const ticket = actions.begin()
    if (ticket) used.add(key)
    return ticket
  }
  const fresh = (ticket, role) => mutationAvailable && mutationNow.current
    && actions.current(ticket) && ready() && rowMatches(role)
  const rowOf = role => (data?.roles || []).find(row => row.role === role)
  const act = async (role, action, confirm) => {
    if (action === 'create') { onInstall?.(); return }
    const ticket = begin(role, action)
    if (!ticket) return
    setBusy(`${role}:${action}`)
    setNote(null)
    try {
      const res = await api.jobAct(rowOf(role), action, confirm)
      if (!fresh(ticket, role)) return
      if (res?.ok) {
        const done = action === 'remove' ? t('wa.jobDoneRemove')
            : action === 'pause' ? t('wa.jobDonePause') : t('wa.jobDoneResume')
        setNote({ tone: 'ok', text: done })
        jobs?.refresh?.()
      } else if (res) {
        const seen = txReason(res.reason || res.error, res.reason_source, t)
        setNote(seen ? { tone: 'bad', ...seen } : { tone: 'bad', text: t('wa.jobFailed') })
      } else {
        setNote({ tone: 'bad', text: t('wa.jobFailed') })
      }
    } catch (e) {
      if (fresh(ticket, role)) setNote({ tone: 'bad', text: errText(e) })
    } finally {
      if (actions.finish(ticket)) setBusy(null)
    }
  }
  const saveSchedule = async (role, expr) => {
    if (editNow.current !== reviewedEdit || reviewedEdit?.role !== role) return
    const ticket = begin(role, 'schedule')
    if (!ticket) return
    setBusy(`${role}:schedule`)
    setNote(null)
    try {
      const res = await api.jobAct(rowOf(role), 'schedule', false, expr)
      if (!fresh(ticket, role)) return
      if (res?.ok) {
        const saved = String(res.schedule || expr)
        editNow.current = null
        setEdit(null)
        setNote({ tone: 'ok', text: t('wa.jobScheduleDone', schedHuman(t, saved), saved) })
        jobs?.refresh?.()
      } else {
        const payload = res || {}
        const seen = txReason(payload.reason || payload.error, payload.reason_source, t)
        setNote({ tone: 'bad', ...(seen || { text: t('wa.jobFailed') }) })
      }
    } catch (e) {
      if (fresh(ticket, role)) setNote({ tone: 'bad', text: errText(e) })
    } finally {
      if (actions.finish(ticket)) setBusy(null)
    }
  }
  const removeJob = async grant => {
    if (armedNow.current !== grant) return
    const role = grant.role
    const ticket = begin(role, 'remove')
    if (!ticket) return
    armedNow.current = null
    setArmed(null)
    setBusy(`${role}:remove`)
    setNote(null)
    try {
      const res = await api.jobAct(rowOf(role), 'remove', true)
      if (!fresh(ticket, role)) return
      if (res?.ok) {
        setNote({ tone: 'ok', text: t('wa.jobDoneRemove') })
        jobs?.refresh?.()
      } else {
        const payload = res || {}
        const seen = txReason(payload.reason || payload.error, payload.reason_source, t)
        setNote({ tone: 'bad', ...(seen || { text: t('wa.jobFailed') }) })
      }
    } catch (e) {
      if (fresh(ticket, role)) setNote({ tone: 'bad', text: errText(e) })
    } finally {
      if (actions.finish(ticket)) setBusy(null)
    }
  }
  if (jobs?.error && !data) {
    return jsx(Failure, { detail: jobs.error, t, text: t('wa.loadFailed') }, 'failed')
  }
  if (!data) return jsx('div', { className: 'wa-body', children: jsx(Loading, {}, 'lw') }, 'loading')
  if (data.ok === false) {
    const seen = txReason(data.reason, data.reason_source, t)
    return jsx(Failure, { detail: seen?.text || data.error, t, text: t('wa.jobsReadFailed') }, 'unread')
  }
  const roles = (data.roles || []).filter(row => !only || row.role === only)
  const zone = data.timezone || null
  const drift = role => (role.live && role.schedule_source === 'store' && role.planned_schedule
    && role.planned_schedule !== role.schedule
    ? jsxs('span', { className: 'wa-job-drift', children: [
      jsx('span', { children: t('wa.jobDriftStore') }, 'a'),
      jsx('span', { className: 'wa-mono', children: role.schedule }, 's'),
      jsx('span', { children: t('wa.jobDriftConfig') }, 'b'),
      jsx('span', { className: 'wa-mono', children: role.planned_schedule }, 'c')
    ] }, 'drift')
    : null)
  const editor = role => (mutationAvailable && edit === role.role && editNow.current === reviewedEdit
    && reviewedEdit?.role === role.role && ready()
    ? jsx(ScheduleEditor, {
      busy: Boolean(busy),
      onCancel: () => {
        if (ready() && editNow.current === reviewedEdit) { editNow.current = null; setEdit(null) }
      },
      onSave: expr => saveSchedule(role.role, expr),
      scopeMatches: () => ready() && rowMatches(role.role) && editNow.current === reviewedEdit,
      role,
      t,
      zone
    }, 'sched')
    : null)
  return jsxs('div', { 'aria-busy': Boolean(busy), children: [
    jsx(Stale, { error: jobs?.error, t }, 'stale'),
    !mutationAvailable ? jsx('div', { className: 'wa-msg', role: 'status',
      children: txReason(data.management_reason, data.reason_source, t)?.text || t('wa.jobReadOnly') }, 'read-only') : null,
    data.cron === false
      ? jsx('div', { className: 'wa-msg wa-bad', children: t('wa.jobNoStore') }, 'nostore')
      : null,
    !only && (data.orphans || []).length
      ? jsx('div', { className: 'wa-msg wa-bad',
        children: t('wa.jobOrphans', data.orphans.length) }, 'orphans')
      : null,
    jsx('div', { 'aria-live': 'polite', className: 'wa-live', children: note
      ? jsxs('div', { 'data-tone': note.tone === 'ok' ? 'ok' : 'bad',
        className: 'wa-help wa-jobs-note', children: [
        jsx('div', { className: 'wa-help-title',
          children: note.tone === 'ok' ? t('wa.helpResult') : t('wa.helpRefused') }, 'h'),
        jsx('div', { className: note.tone === 'ok' ? 'wa-msg' : 'wa-msg wa-bad',
          children: (busy ? `${t('wa.working')} ` : '') + note.text }, 'm'),
        note.raw && note.raw !== note.text
          ? jsx(Tip, { label: note.raw, children: jsxs('div', { className: 'wa-raw', children: [
            jsxs('div', { className: 'wa-code-head', children: [
              jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, 'c'),
              Copy({ copyKey: 'j', text: note.raw })
            ] }, 'ch'),
            jsx(PanelBlock, { className: 'wa-mono', children: note.raw }, 'p')
          ] }, 'raw') }, 'rt')
          : null
      ] }, 'note')
      : null }, 'live'),
    mutationAvailable && armed && armedNow.current === armed && ready() && rowMatches(armed.role)
      ? jsx(ConfirmDialog, {
        open: true,
        destructive: true,
        title: t('wa.jobAsk'),
        description: t('wa.jobDeleteHint'),
        confirmLabel: t('wa.jobConfirm'),
        cancelLabel: t('wa.jobCancel'),
        onClose: () => {
          if (ready() && armedNow.current === armed) { armedNow.current = null; setArmed(null) }
        },
        onConfirm: () => removeJob(armed)
      }, 'confirm')
      : null,
    only ? roles.map(role => jsxs('div', { className: 'wa-metro-jobctl', 'data-role': role.role, children: [
      role.live ? jsxs('div', { className: 'wa-metro-acts', children: [
        jsx(Button, { className: 'wa-job-act wa-metro-changetime', variant: 'outline',
          disabled: Boolean(busy) || !actionable(), 'aria-expanded': edit === role.role,
          onClick: () => {
            if (!actionable() || !rowMatches(role.role)) return
            editNow.current = editNow.current?.role === role.role ? null : { role: role.role }
            setNote(null); setEdit(editNow.current?.role || null)
          }, children: t('wa.metroChangeTime') }, 's'),
        jsx(Button, { className: 'wa-job-act wa-metro-pause', variant: 'outline',
          disabled: Boolean(busy) || !actionable(),
          onClick: () => act(role.role, role.state === 'paused' ? 'resume' : 'pause'),
          children: role.state === 'paused' ? t('wa.metroResume') : t('wa.metroPause') }, 'p')
      ] }, 'acts') : null,
      drift(role),
      editor(role)
    ] }, role.role)) : roles.map(role => jsxs('details', { className: 'wa-job', children: [
      jsxs('summary', { className: 'wa-job-summary', children: [
        jsx('span', { className: 'wa-job-glyph', children: icon(role.kind === 'agent' ? 'shield' : 'watch') }, 'icon'),
        jsx('strong', { children: role.name }, 'name'),
        jsx('span', { className: 'wa-job-summary-schedule', children: role.schedule
          ? schedHuman(t, role.schedule) : t('wa.jobNoSchedule') }, 'schedule'),
        jsx('span', { className: 'wa-job-summary-state', 'data-tone': role.live && !role.target?.ok ? 'bad' : 'quiet',
          children: role.live && !role.target?.ok ? t('wa.jobAttention')
            : role.live ? role.state === 'paused' ? t('wa.jobPausedState') : t('wa.jobLiveState')
              : t('wa.jobNoId') }, 'state'),
        icon('chevron-down')
      ] }, 'summary'),
      jsxs('div', { className: 'wa-job-expanded', children: [
      jsxs('span', { className: 'wa-job-main', children: [
        jsxs('span', { className: 'wa-job-line', children: [
          jsx('span', { className: 'wa-clip wa-job-name', children: role.name }, 'n'),
          role.kind === 'agent' ? Status({ text: t('wa.jobAgent'), variant: 'muted', badgeKey: 'k' }) : null,
          role.live
            ? Status({
              text: role.state === 'paused' ? t('wa.jobPausedState') : t('wa.jobLiveState'),
              variant: role.state === 'paused' ? 'warn' : 'muted',
              badgeKey: 's'
            })
            : null,
          role.live && !role.target?.ok
            ? Status({
              text: role.target?.root_ok
                ? t('wa.jobScriptMissing', role.target?.impl || '')
                : t('wa.jobRootMissing'),
              variant: 'destructive',
              badgeKey: 't'
            })
            : null
        ] }, 'l'),
        jsxs('span', { className: 'wa-job-sched', children: [
          jsx('span', { className: 'wa-job-human',
            children: role.schedule ? schedHuman(t, role.schedule) : t('wa.jobNoSchedule') }, 'h'),
          role.schedule
            ? jsx(Tip, { label: t('wa.schCronTip'), children: jsx('span', { className: 'wa-mono wa-job-cron',
              tabIndex: 0, children: role.schedule }, 'c') }, 'ct')
            : null,
          jsx('span', { className: 'wa-clip wa-job-meta',
            children: `${role.id ? `${t('wa.jobId')} ${role.id.slice(0, 8)}` : t('wa.jobNoId')}${!role.live
              && role.kind === 'agent' ? ` · ${t('wa.jobAgentNote')}` : ''}` }, 'm')
        ] }, 's'),
        role.live ? jsx(JobRunLine, { role, t }, 'r') : null
      ] }, 'main'),
      jsxs('span', { className: 'wa-job-acts', children: [
        role.live
          ? jsx(RowButton, {
            className: 'wa-job-act',
            disabled: Boolean(busy) || !actionable(),
            onClick: () => act(role.role, role.state === 'paused' ? 'resume' : 'pause'),
            children: role.state === 'paused' ? t('wa.jobResume') : t('wa.jobPause')
          }, 'p')
          : role.kind === 'agent' ? null : jsx(RowButton, {
            className: 'wa-job-act wa-act-last',
            disabled: Boolean(busy) || !actionable(),
            onClick: () => act(role.role, 'create'),
            children: t('wa.jobCreate')
          }, 'c'),
        role.live
          ? jsx(RowButton, {
            className: 'wa-job-act',
            disabled: Boolean(busy) || !actionable(),
            onClick: () => {
              if (!actionable() || !rowMatches(role.role)) return
              editNow.current = editNow.current?.role === role.role ? null : { role: role.role }
              setNote(null); setEdit(editNow.current?.role || null)
            },
            children: t('wa.jobSchedule')
          }, 's')
          : null,
        role.live && role.kind !== 'agent'
          ? jsx(RowButton, {
            className: 'wa-job-act wa-bad',
            disabled: Boolean(busy) || !actionable(),
            onClick: () => {
              if (!actionable() || !rowMatches(role.role)) return
              const grant = { role: role.role }
              armedNow.current = grant; setArmed(grant)
            },
            children: t('wa.jobDelete')
          }, 'd')
          : null
      ] }, 'acts'),
      drift(role),
      editor(role)
      ] }, 'expanded')
    ] }, role.role))
  ] })
}

const icon = codicon => jsx('i', { 'aria-hidden': true, className: `codicon codicon-${codicon}` }, codicon)

function candKind(t, kind) {
  if (kind === 'correction') return { text: t('wa.candCorrection'), variant: 'muted' }
  if (kind === 'new') return { text: t('wa.candNew'), variant: 'success' }
  if (kind === 'update') return { text: t('wa.candUpdate'), variant: 'muted' }
  if (kind === 'retire') return { text: t('wa.candRetire'), variant: 'warn' }
  return { text: String(kind || '—'), variant: 'muted' }
}


function RawBlock({ t, copyKey, text }) {
  return jsx(Tip, { label: text, children: jsxs('div', { className: 'wa-raw', children: [
    jsxs('div', { className: 'wa-code-head', children: [
      jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, 'c'),
      Copy({ copyKey, text })
    ] }, 'ch'),
    jsx(PanelBlock, { className: 'wa-mono', children: text }, 'p')
  ] }, 'raw') }, 'rt')
}

function RequestSource({ text }) {
  const pinned = /^([^@\s]+@)([0-9a-f]{40})(:.*)$/.exec(text)
  if (!pinned) return jsx('span', { className: 'wa-mono wa-request-source', children: text })
  return jsxs('span', { className: 'wa-mono wa-request-source', children: [
    pinned[1],
    jsx('span', { className: 'wa-sha-full', children: pinned[2] }, 'full'),
    jsx('span', { className: 'wa-sha-short', children: `${pinned[2].slice(0, 7)}…` }, 'short'),
    pinned[3]
  ] })
}

function EvidenceRequests({ t, requests, failures }) {
  if (!requests.length) return null
  const failed = failures || {}
  return jsxs('section', { className: 'wa-requests', 'aria-label': t('wa.candRequests'), children: [
    jsx('h4', { className: 'wa-sec-title', children: t('wa.candRequests') }, 'title'),
    jsx('p', { className: 'wa-desk-summary', children: t('wa.candRequestsHint') }, 'hint'),
    ...requests.map(request => {
      const sources = Array.isArray(request.github) ? request.github : request.url ? [request.url] : []
      const state = request.fetched ? 'fetched' : failed[request.id] ? 'failed' : 'waiting'
      return jsxs('div', { className: 'wa-request', 'data-request': request.id, 'data-state': state, children: [
        jsxs('p', { className: 'wa-request-head', children: [
          jsx('span', { className: 'wa-mono', children: request.id }, 'id'), ' ',
          jsx('span', { className: 'wa-request-state',
            children: state === 'fetched' ? t('wa.candRequestFetched') : state === 'failed'
              ? `${t('wa.candRequestFailed')} ${failed[request.id]}` : t('wa.candRequestWaiting') }, 'state')
        ] }, 'head'),
        jsx(PanelMeta, { className: 'wa-kv', rows: [
          { label: t('wa.candRequestSupports'), value: String(request.supports || '') },
          { label: t('wa.candRequestSource'), value: jsx('span', { children: sources.map((text, at) =>
            jsx(RequestSource, { text }, String(at))) }) },
          { label: t('wa.candRequestPassages'), value: jsx('span', { children: (request.passages || []).map((text, at) =>
            jsx('q', { className: 'wa-request-passage', children: text }, String(at))) }) }
        ] }, 'facts')
      ] }, request.id)
    })
  ] }, 'requests')
}

function CandidateDetail({ t, detail, children }) {
  const [view, setView] = useState('proposal')
  useEffect(() => setView('proposal'), [detail.data?.ref])
  if (detail.error) return jsxs('div', { children: [
    jsx(Failure, { detail: detail.error, t, text: t('wa.candShowFailed') }, 'failed'),
    children
  ] })
  if (!detail.data) return jsx(Loading, {}, 'lw')
  const data = detail.data
  const lines = data.diff || []
  const diff = lines.join('\n')
  const probs = data.format_problems || []
  const folders = data.evidence_folders || []
  const why = String(data.candidate?.why || '')
  const heading = lines.find(line => /^[+ ]# /.test(line))
  const title = heading ? heading.slice(3) : data.candidate?.summary || data.ref
  const readable = lines.filter((line, index) => !(index < 2 && /^(--- |\+\+\+ )/.test(line))
    && !/^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@/.test(line))
  const rows = [

    { label: t('wa.candEvidence'), value: jsx('span', { className: folders.length ? 'wa-mono' : '',
      children: folders.length ? folders.join(', ') : t('wa.candEvidenceNone') }) },
    { label: t('wa.candTarget'), value: jsxs('span', { className: 'fl-destination', children: [
      jsx('span', { className: 'wa-mono', children: data.candidate?.target || data.ref }, 'file'),
      jsx('span', { children: data.target_exists ? t('wa.candTargetExists') : t('wa.candTargetNew') }, 'state')
    ] }, 'destination') },
    { label: t('wa.candFormat'), value: probs.length
      ? jsx('span', { className: 'wa-bad', children: probs.join(' · ') })
      : t('wa.candFormatOk') }
  ]
  return jsxs('div', { className: 'fl-review', children: [
    jsxs('section', { className: 'fl-change', 'aria-label': t('wa.folioDocument'), children: [
      jsxs('header', { className: 'fl-document-head', children: [
        jsxs('div', { className: 'fl-document-top', children: [
          jsx('span', { children: candKind(t, data.corrects ? 'correction' : data.candidate?.kind).text }, 'kind'),
          jsx('span', { children: t('wa.folioDraft') }, 'draft')
        ] }, 'top'),
        jsx('h2', { children: title }, 'title'),
        data.candidate?.summary && data.candidate.summary !== title
          ? jsx('p', { className: 'fl-summary', children: data.candidate.summary }, 'summary') : null,
        jsx('p', { className: 'fl-file wa-mono', children: data.candidate?.target || data.ref }, 'target')
      ] }, 'head'),
      jsxs('div', { className: 'fl-views', 'aria-label': t('wa.folioDocument'), children: [
        jsx('button', { type: 'button', 'aria-pressed': view === 'proposal', onClick: () => setView('proposal'),
          children: t('wa.folioProposal') }, 'proposal'),
        jsx('button', { type: 'button', 'aria-pressed': view === 'reason', onClick: () => setView('reason'),
          children: t('wa.folioReason') }, 'reason')
      ] }, 'views'),
      view === 'proposal' ? jsxs('div', { className: 'fl-proposal', tabIndex: 0,
        'aria-label': t('wa.candDiff'), children: [
        readable.length ? readable.map((line, index) => {
          const sign = /^[+\- ]/.test(line) ? line[0] : ' '
          const text = /^[+\- ]/.test(line) ? line.slice(1) : line
          const headingLine = /^(#{1,6})\s+(.*)$/.exec(text)
          return jsxs('div', { className: 'fl-line', 'data-change': sign === '+' ? 'added'
            : sign === '-' ? 'removed' : 'context', children: [
            jsx('span', { className: 'fl-gutter', children: sign.trim() || '·' }, 'sign'),
            jsx('span', { className: headingLine ? 'fl-line-heading' : 'fl-line-text',
              'data-level': headingLine ? String(headingLine[1].length) : undefined,
              children: headingLine ? headingLine[2] : text || '\u00a0' }, 'text')
          ] }, String(index))
        }) : jsx('p', { children: t('wa.candNoDiff') }, 'none'),
        jsxs('details', { className: 'fl-original', children: [
          jsx('summary', { children: t('wa.checkAsWritten') }, 'summary'),
          jsx(RawBlock, { t, copyKey: 'd', text: diff || t('wa.candNoDiff') }, 'raw')
        ] }, 'original')
      ] }, 'proposal') : jsxs('div', { className: 'fl-reason', children: [
        jsx('h3', { children: t('wa.candWhy') }, 'title'),
        jsx('p', { children: why || '—' }, 'why'),
        jsx('h3', { children: t('wa.candEvidence') }, 'evidence-title'),
        jsx('p', { className: 'wa-mono', children: folders.length ? folders.join(', ')
          : t('wa.candEvidenceNone') }, 'evidence')
      ] }, 'reason'),
      jsxs('div', { className: 'fl-checks', children: [
        jsx('span', { children: probs.length ? t('wa.candFormatBlocked') : t('wa.candFormatOk') }, 'format'),
        jsx('span', { children: t('wa.folioEvidenceCount', folders.length) }, 'count')
      ] }, 'checks'),
      jsxs('footer', { className: 'fl-approval', children: [
        jsx('p', { className: 'fl-warning', children: t('wa.candPublishWarning') }, 'warning'),
        children
      ] }, 'approval')
    ] }, 'change'),
    jsxs('aside', { className: 'fl-decision', 'aria-label': t('wa.folioDecision'), children: [
      jsx('h3', { className: 'wa-sec-title', children: t('wa.folioDecision') }, 'head'),
      jsxs('ol', { className: 'fl-trail', children: [
        jsxs('li', { children: [
          jsx('span', { className: 'fl-trail-point', children: icon('file-text') }, 'point'),
          jsxs('span', { className: 'fl-trail-copy', children: [
            jsx('strong', { children: t('wa.folioCollected') }, 'title'),
            jsx('span', { children: folders.length ? t('wa.folioEvidenceCount', folders.length)
              : t('wa.candEvidenceNone') }, 'evidence')
          ] }, 'copy')
        ] }, 'collected'),
        jsxs('li', { children: [
          jsx('span', { className: 'fl-trail-point', children: icon('edit') }, 'point'),
          jsxs('span', { className: 'fl-trail-copy', children: [
            jsx('strong', { children: t('wa.folioCandidateCreated') }, 'title'),
            jsx('span', { children: why || '—' }, 'why')
          ] }, 'copy')
        ] }, 'candidate'),
        jsxs('li', { children: [
          jsx('span', { className: 'fl-trail-point', children: icon('shield') }, 'point'),
          jsxs('span', { className: 'fl-trail-copy', children: [
            jsx('strong', { children: t('wa.folioYourDecision') }, 'title'),
            jsx('span', { children: t('wa.folioPendingReview') }, 'pending')
          ] }, 'copy')
        ] }, 'decision')
      ] }, 'trail'),
      jsx('div', { className: 'fl-facts', children: jsx(PanelMeta, { className: 'wa-kv', rows }, 'kv') }, 'facts')
    ] }, 'decision')
  ] }, 'detail')
}

function CandidatesCard({ t, cands, initialRef, scope, onShown, engineUpdate: updateReady }) {
  const data = cands?.data || null
  const list = data?.candidates || []
  const [open, setOpen] = useState(null)
  const [detail, setDetail] = useState({ data: null, error: null })
  const [armed, setArmed] = useState(null)
  const [rejecting, setRejecting] = useState(false)
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const [consumed, setConsumed] = useState([])
  const [fetchFailures, setFetchFailures] = useState({})
  const request = useRef(0)
  const selected = useRef(null)
  const inFlight = useRef(false)
  const alive = useRef(true)
  const latest = useRef(null)
  const confirmation = useRef(null)
  const decisionEpoch = useRef(0)
  const renderedEpoch = decisionEpoch.current
  const available = list.filter(row => !consumed.includes(row.ref))
  const row = available.find(item => item.ref === open)
  const matching = Boolean(row && detail.data?.ref === open)
  const readable = data?.ok === true && !cands?.error
  const unreviewable = Boolean(row && !detail.data && detail.error)
  latest.current = { readable, list: available, detail: detail.data, open, polling: cands?.busy, unreviewable }
  const shownRef = matching ? detail.data.ref : null
  useLayoutEffect(() => { onShown?.(shownRef) }, [shownRef])
  useEffect(() => () => onShown?.(null), [])

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; request.current += 1; selected.current = null }
  }, [])

  const resetDecision = () => {
    confirmation.current = null
    decisionEpoch.current += 1
    setArmed(null)
    setRejecting(false)
    setWhy('')
  }
  const select = async ref => {
    if (inFlight.current || !scope?.matches()) return
    const ticket = ++request.current
    selected.current = ref
    setOpen(ref)
    setDetail({ data: null, error: null })
    resetDecision()
    if (!ref) return
    try {
      const res = await api.candShow(ref)
      if (!alive.current || !scope?.matches() || ticket !== request.current || selected.current !== ref
        || !latest.current?.list.some(item => item.ref === ref)) return
      if (res?.ok && res.ref === ref) setDetail({ data: res, error: null })
      else setDetail({ data: null, error: res?.error || t('wa.candShowFailed') })
    } catch (error) {
      if (alive.current && scope?.matches() && ticket === request.current) {
        setDetail({ data: null, error: errText(error) })
      }
    }
  }

  useEffect(() => {
    resetDecision()
    if (!readable) return
    const next = available.find(item => item.ref === selected.current)?.ref
      || available.find(item => item.ref === initialRef)?.ref || available[0]?.ref || null
    if (inFlight.current) {
      if (!available.some(item => item.ref === selected.current)) {
        request.current += 1
        selected.current = null
        setOpen(null)
        setDetail({ data: null, error: null })
      }
      return
    }
    void select(next)
  }, [data, cands?.error])

  const canAct = (ref, action) => {
    const now = latest.current
    return alive.current && scope?.matches() && now?.readable && !now.polling
      && selected.current === ref && now.open === ref
      && now.list.some(item => item.ref === ref)
      && (now.detail?.ref === ref || action === 'reject' && now.unreviewable)
      && (action !== 'approve' || Array.isArray(now.detail.format_problems) && !now.detail.format_problems.length
        && !(Array.isArray(now.detail.pending_evidence) && now.detail.pending_evidence.length)
        && typeof now.detail.approval_refusal !== 'string')
      && (action !== 'fetch_evidence' || Array.isArray(now.detail.pending_evidence) && now.detail.pending_evidence.length > 0)
  }
  const settle = (res, done, ref) => {
    if (res?.ok) {
      setNote({ tone: 'ok', text: done, raw: res.output || null })
      setConsumed(previous => previous.includes(ref) ? previous : previous.concat(ref))
      request.current += 1
      selected.current = null
      setOpen(null)
      setDetail({ data: null, error: null })
      resetDecision()
      cands?.refresh?.()
      return true
    }
    const payload = res || {}
    const seen = txReason(payload.reason || payload.error, payload.reason_source, t)
    setNote({ tone: 'bad', text: seen ? seen.text : t('wa.candFailed'), raw: payload.output || seen?.raw || null })
    return false
  }
  const act = async (ref, action, confirm = false) => {
    if (renderedEpoch !== decisionEpoch.current) return
    if (inFlight.current || !canAct(ref, action) || action === 'reject' && !why.trim()) return
    if (confirm && (armed?.ref !== ref || confirmation.current !== armed)) return
    const epoch = decisionEpoch.current
    const reviewDigest = latest.current?.detail?.review_digest
    const withoutReview = action === 'reject' && !confirm && latest.current?.unreviewable === true
    if (!withoutReview && (typeof reviewDigest !== 'string' || !/^[0-9a-f]{64}$/.test(reviewDigest))) {
      setNote({ tone: 'bad', text: t('wa.candOwnerUnavailable') })
      resetDecision()
      return
    }
    if (confirm && (armed?.reviewDigest !== reviewDigest || !armed?.requestId)) {
      resetDecision()
      return
    }
    if (confirm) confirmation.current = null
    inFlight.current = true
    setBusy(true)
    setNote(null)
    try {
      const res = await api.candAct(ref, action, confirm, action === 'reject' ? why.trim() : undefined,
        withoutReview ? undefined : reviewDigest, confirm ? armed?.requestId : undefined)
      if (!alive.current || !scope?.matches()) return
      if (res?.needs_confirm && action === 'approve' && !confirm) {
        if (!canAct(ref, action) || epoch !== decisionEpoch.current) return
        if (res.review_digest !== reviewDigest || typeof res.request_id !== 'string' || !res.request_id) {
          settle({ ok: false, reason: t('wa.candOwnerUnavailable') }, '', ref)
          resetDecision()
          return
        }
        const ask = txReason(res.reason, res.reason_source, t)
        const decision = { ref, reviewDigest, requestId: res.request_id,
          text: ask ? ask.text : t('wa.candApproveAsk'), output: res.output || '' }
        confirmation.current = decision
        setArmed(decision)
      } else {
        settle(res, action === 'approve' ? t('wa.candApproved') : t('wa.candRejected'), ref)
        if (confirm && action === 'approve' && res?.ok === false && res?.retryable === true
          && canAct(ref, action) && epoch === decisionEpoch.current) {
          confirmation.current = armed
          setArmed(armed)
        } else setArmed(null)
      }
    } catch (error) {
      if (alive.current && scope?.matches()) {
        if (confirm && action === 'approve' && canAct(ref, action) && epoch === decisionEpoch.current) {
          confirmation.current = armed
          setArmed(armed)
        } else setArmed(null)
        setNote({ tone: 'bad', text: errText(error) })
      }
    } finally {
      inFlight.current = false
      if (alive.current) setBusy(false)
    }
  }
  const fetchEvidence = async ref => {
    if (renderedEpoch !== decisionEpoch.current || inFlight.current || !canAct(ref, 'fetch_evidence')) return
    const reviewDigest = latest.current?.detail?.review_digest
    if (typeof reviewDigest !== 'string' || !/^[0-9a-f]{64}$/.test(reviewDigest)) return
    inFlight.current = true
    setBusy(true)
    setNote(null)
    try {
      const res = await api.candFetch(ref, reviewDigest)
      if (!alive.current || !scope?.matches()) return
      const failures = {}
      for (const item of Array.isArray(res?.results) ? res.results : []) {
        if (item && item.ok === false && item.id) failures[item.id] = String(item.error || '')
      }
      setFetchFailures(previous => ({ ...previous, [ref]: failures }))
      if (res?.ok) setNote({ tone: 'ok', text: t('wa.candFetchDone') })
      else {
        const payload = res || {}
        const seen = txReason(payload.reason || payload.error, payload.reason_source, t)
        setNote({ tone: 'bad', text: seen ? seen.text : t('wa.candFailed'), raw: payload.output || seen?.raw || null })
      }
    } catch (error) {
      if (alive.current && scope?.matches()) setNote({ tone: 'bad', text: errText(error) })
    } finally {
      inFlight.current = false
      if (alive.current) {
        setBusy(false)
        if (selected.current === ref) void select(ref)
      }
    }
  }
  if (cands?.error && !data) return jsx(Failure, { detail: cands.error, t, text: t('wa.candReadFailed') }, 'failed')
  if (!data) return jsx('div', { className: 'wa-body', children: jsx(Loading, {}, 'lw') }, 'loading')
  if (data.ok === false) return jsx(Failure, { detail: data.error, t, text: t('wa.candReadFailed') }, 'unread')
  const actionable = matching && readable && !busy && !cands?.busy
  const rejectable = actionable || unreviewable && readable && !busy && !cands?.busy
  const requests = matching && Array.isArray(detail.data?.evidence_requests) ? detail.data.evidence_requests : []
  const pendingEvidence = matching && Array.isArray(detail.data?.pending_evidence) ? detail.data.pending_evidence : []
  const refusal = matching && !pendingEvidence.length && typeof detail.data?.approval_refusal === 'string'
    ? detail.data.approval_refusal : null
  const approveAllowed = actionable && Array.isArray(detail.data?.format_problems)
    && !detail.data.format_problems.length && !pendingEvidence.length && !refusal
  const primary = pendingEvidence.length
    ? jsx(Button, { disabled: !actionable, onClick: () => fetchEvidence(open), size: 'sm', variant: 'default',
      children: busy ? t('wa.candFetching') : t('wa.candFetch', pendingEvidence.length) }, 'fetch')
    : jsx(Button, { disabled: !approveAllowed, onClick: () => act(open, 'approve'), size: 'sm',
      variant: 'default', children: t('wa.candApprove') }, 'approve')
  const noteBlock = jsx('div', { 'aria-live': 'polite', className: 'wa-live', children: note
    ? jsxs('div', { 'data-tone': note.tone === 'ok' ? 'ok' : 'bad', className: 'wa-help', children: [
      jsx('div', { className: 'wa-help-title',
        children: note.tone === 'ok' ? t('wa.helpResult') : t('wa.helpRefused') }, 'h'),
      jsx('div', { className: note.tone === 'ok' ? 'wa-msg' : 'wa-msg wa-bad', children: note.text }, 'm'),
      note.raw && note.raw !== note.text ? jsx(RawBlock, { copyKey: 'n', t, text: note.raw }, 'raw') : null
    ] }, 'note') : null }, 'live')
  const actions = rejecting ? jsxs('div', { className: 'wa-confirm', children: [
    jsx(Input, { 'aria-label': t('wa.candRejectReason'), disabled: !rejectable,
      onChange: e => setWhy(e.target.value), placeholder: t('wa.candRejectReason'), size: 'sm', value: why }, 'reason'),
    jsxs('div', { className: 'wa-pend-acts', children: [
      jsx(Button, { disabled: !rejectable || !why.trim(), onClick: () => act(open, 'reject'), size: 'sm',
        variant: 'default', children: t('wa.candRejectSend') }, 'send'),
      jsx(Button, { disabled: busy, onClick: resetDecision, size: 'sm', variant: 'outline',
        children: t('wa.jobCancel') }, 'cancel')
    ] }, 'buttons')
  ] }, 'reject') : jsxs('div', { className: 'wa-pend-acts', children: [
    jsx(Button, { disabled: !rejectable, onClick: () => { setArmed(null); setRejecting(true) }, size: 'sm',
      variant: 'outline', children: t('wa.candReject') }, 'reject'),
    primary
  ] }, 'actions')
  const index = available.findIndex(item => item.ref === open)
  const later = () => {
    if (busy || inFlight.current || available.length < 2) return
    setNote(null)
    void select(available[(index + 1) % available.length].ref)
  }
  const step = by => {
    const next = available[index + by]
    if (busy || inFlight.current || available.length < 2 || index < 0 || !next) return
    setNote(null)
    void select(next.ref)
  }
  const stepButton = (by, glyph, label) => jsx(Tip, { label, children: jsx(Button, { 'aria-label': label,
    disabled: busy || available.length < 2 || index < 0 || !available[index + by],
    onClick: () => step(by), size: 'icon-sm', variant: 'outline', children: icon(glyph) }) }, `step-${by}`)
  const shownKind = row?.corrects ? 'correction' : row?.kind
  const kind = row ? candKind(t, shownKind) : null
  const draftName = ref => String(ref || '').split('/').pop()
  const rowNote = !row ? null : row.blocked
    ? jsxs('p', { className: 'fl-warning', 'data-draft-note': 'blocked', children: [
      t('wa.candBlocked'), ' ', row.blocked] }, 'draft-note')
    : row.stale
      ? jsxs('p', { className: 'fl-warning', 'data-draft-note': 'stale', children: [
        t('wa.candStaleDraft'), ' ', row.stale] }, 'draft-note')
    : row.superseded_by
      ? jsx('p', { className: 'fl-warning', 'data-draft-note': 'superseded',
        children: t('wa.candSuperseded', draftName(row.superseded_by)) }, 'draft-note')
      : row.derived_from
        ? jsx('p', { className: 'wa-desk-summary', 'data-draft-note': 'rederived',
          children: t('wa.candRederived', draftName(row.derived_from)) }, 'draft-note')
      : row.corrects
        ? jsx('p', { className: 'wa-desk-summary', 'data-draft-note': 'correction',
          children: t('wa.candCorrects', draftName(row.corrects)) }, 'draft-note')
        : null
  const heading = matching ? (detail.data.diff || []).find(line => /^[+ ]# /.test(line)) : null
  const draftTitle = heading ? heading.slice(3) : row?.summary || row?.ref || ''
  const steps = available.length <= 8 ? available.map((item, at) => jsx('span', { className: 'wa-desk-step',
    'data-on': at === index ? '1' : undefined, 'aria-hidden': true }, item.ref)) : []
  return jsxs('div', { className: 'fl-desk', 'aria-busy': busy, children: [
    jsx(Stale, { error: cands?.error, t }, 'stale'),
    noteBlock,
    armed && approveAllowed && armed.ref === open ? jsx(ConfirmDialog, {
      open: true, title: t('wa.metroApproveAsk'),
      children: jsxs('div', { className: 'fl-confirm wa-approve', children: [
        jsx('p', { children: t('wa.metroApproveWrites', draftTitle || row?.target || open) }, 'ask'),
        jsx('p', { className: 'wa-mono wa-approve-path', children: row?.target || open }, 'target'),
        jsxs('p', { className: 'wa-approve-warn', children: [icon('warning'),
          jsx('span', { children: t('wa.metroApproveCredits') }, 'text')] }, 'warning'),
        jsxs('details', { className: 'wa-metro-raw', children: [
          jsx('summary', { children: t('wa.metroApproveEngine') }, 'summary'),
          jsx('p', { children: armed.text }, 'engine-ask'),
          jsx('p', { children: t('wa.candPublishWarning') }, 'engine-warning'),
          armed.output ? jsx(RawBlock, { copyKey: 'dry-run', t, text: armed.output }, 'output') : null
        ] }, 'engine')
      ] }, 'description'),
      confirmLabel: t('wa.candApproveYes'), cancelLabel: t('wa.jobCancel'),
      onClose: resetDecision, onConfirm: () => act(armed.ref, 'approve', true)
    }, 'confirm') : null,
    available.length && row ? jsxs('article', { className: 'wa-desk wa-pend-detail', id: 'wa-review-document',
      'aria-label': t('wa.deskLabel'), 'data-candidate-ref': matching ? detail.data.ref : undefined, children: [
        jsxs('div', { className: 'wa-desk-top', children: [
          unreviewable ? null : jsxs('span', { className: 'wa-desk-kind', 'data-kind': shownKind, children: [
            icon(shownKind === 'retire' ? 'close' : shownKind === 'new' ? 'new-file' : 'edit'),
            jsx('span', { children: kind.text }, 'text')
          ] }, 'kind'),
          ' ',
          jsxs('span', { className: 'wa-desk-steps', children: [
            ...steps,
            stepButton(-1, 'chevron-left', t('wa.deskPrevious')),
            jsx('span', { className: 'wa-desk-count', children: t('wa.deskPosition', index + 1, available.length) },
              'count'),
            stepButton(1, 'chevron-right', t('wa.deskNext'))
          ] }, 'steps')
        ] }, 'top'),
        ' ',
        jsxs('div', { children: [
          jsx('h3', { className: 'wa-desk-title', children: draftTitle }, 'title'),
          row.summary && row.summary !== draftTitle
            ? jsx('p', { className: 'wa-desk-summary', children: row.summary }, 'summary') : null,
          rowNote,
          unreviewable ? jsx(Failure, { t, text: t('wa.deskUnreadable'), detail: String(detail.error) }, 'unreadable')
            : null,
          unreviewable && updateReady && String(detail.error).includes('New source target already exists')
            ? jsx('p', { className: 'wa-desk-summary', 'data-draft-note': 'engine-fix',
              children: t('wa.deskEngineFix') }, 'engine-fix') : null
        ] }, 'heading'),
        jsxs('p', { className: 'wa-desk-path', children: [
          jsx('span', { children: t('wa.deskSavedAs') }, 'label'), ' ',
          jsx('span', { className: 'wa-mono', children: row.target || row.ref }, 'path')
        ] }, 'path'),
        !readable ? jsx('p', { className: 'fl-warning', children: t('wa.candStale') }, 'stale-action') : null,
        jsx(EvidenceRequests, { t, requests, failures: fetchFailures[open] }, 'requests'),
        refusal ? jsxs('div', { className: 'fl-warning wa-refusal', role: 'note', children: [
          jsx('p', { className: 'wa-refusal-head', children: t('wa.candRefusal') }, 'head'),
          jsx('p', { className: 'wa-refusal-text', children: refusal }, 'text'),
          jsx('p', { className: 'wa-refusal-hint', children: t('wa.candRefusalHint') }, 'hint')
        ] }, 'refusal') : null,
        jsxs('div', { className: 'wa-desk-row', children: [
          jsxs('div', { className: 'wa-desk-acts', children: [
            rejecting ? actions : jsxs('div', { className: 'wa-pend-acts', children: [
              pendingEvidence.length
                ? jsx(Button, { disabled: !actionable, onClick: () => fetchEvidence(open), variant: 'default',
                  children: busy ? t('wa.candFetching') : t('wa.candFetch', pendingEvidence.length) }, 'fetch')
                : jsx(Button, { disabled: !approveAllowed, onClick: () => act(open, 'approve'),
                  variant: 'default', children: t('wa.candApprove') }, 'approve'),
              jsx(Button, { disabled: !rejectable, onClick: () => { setArmed(null); setRejecting(true) },
                variant: 'outline', children: t('wa.candReject') }, 'reject')
            ] }, 'buttons'),
            jsx(Button, { disabled: busy || available.length < 2, onClick: later,
              variant: 'outline', children: t('wa.deskLater') }, 'later')
          ] }, 'acts'),
          jsxs('details', { className: 'wa-desk-more', children: [
            jsxs('summary', { children: [icon('chevron-right'),
              jsx('span', { children: t('wa.deskMore') }, 'text')] }, 'summary'),
            jsx(CandidateDetail, { t, detail: matching ? detail : { data: null, error: detail.error } }, 'detail')
          ] }, `more-${row.ref}`)
        ] }, 'row')
      ] }, 'document') : available.length ? jsx(Loading, {}, 'pick')
      : jsx(EmptyState, { title: t('wa.candNone'), description: t('wa.candNoneHint') }, 'empty')
  ] }, 'desk')
}

function RecoveryList({ t, onComplete, inventory, scope }) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const inFlight = useRef(false)
  const alive = useRef(true)
  const latest = useRef(inventory)
  const completed = useRef(new Set())
  latest.current = inventory
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const resume = async requestId => {
    const now = latest.current
    if (!alive.current || !scope?.matches() || inFlight.current || now.busy || now.error || now.data?.ok !== true
      || inventory.data !== now.data || completed.current.has(requestId)
      || !now.data.operations?.some(row => row.request_id === requestId)) return
    inFlight.current = true
    setBusy(true)
    setNote(null)
    try {
      const result = await api.recover(requestId)
      if (!alive.current || !scope?.matches()) return
      const payload = result || {}
      const seen = txReason(payload.reason, payload.reason_source, t)
      setNote({ tone: payload.ok ? 'ok' : 'bad', text: payload.ok ? t('wa.recoveryDone')
        : seen?.text || t('wa.candFailed') })
      if (result?.ok) { completed.current.add(requestId); inventory.refresh(); onComplete?.() }
    } catch (error) {
      if (alive.current && scope?.matches()) setNote({ tone: 'bad', text: errText(error) })
    } finally {
      inFlight.current = false
      if (alive.current) setBusy(false)
    }
  }
  if (!note && !inventory.error && inventory.data?.ok !== false && !inventory.data?.operations?.length) return null
  const unread = inventory.error || inventory.data?.ok === false
  return jsxs('section', { 'data-recovery-list': true, className: unread ? 'wa-recovery-unread' : 'wa-body', children: [
    unread ? null : jsx('h2', { children: t('wa.recoveryTitle') }, 'title'),
    note ? jsx('div', { className: `wa-msg wa-${note.tone}`, role: 'status', children: note.text }, 'note') : null,
    inventory.error || inventory.data?.ok === false
      ? jsx(Failure, { t, text: t('wa.recoveryReadFailed'), detail: inventory.error
        || txReason(inventory.data.reason, inventory.data.reason_source, t)?.text || t('wa.candFailed') }, 'error')
      : jsx('div', { style: { maxHeight: '160px', overflowY: 'auto' }, children:
        (inventory.data?.operations || []).map(row => jsxs('div', { className: 'wa-pend', children: [
          jsx('span', { children: `${row.ref} · ${row.kind} · ${row.target} · ${row.state}` }, 'label'),
          jsx(Button, { size: 'sm', variant: 'outline', disabled: busy || inventory.busy,
            onClick: () => resume(row.request_id), children: t('wa.recoveryResume') }, 'resume')
        ] }, row.request_id)) }, 'rows'),
  ] }, 'recovery')
}

const RESTART_WAIT_MS = 120000
const RESTART_POLL_MS = 5000

function OwnerSetup({ t, setup, scope, onComplete, onReload }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const [restart, setRestart] = useState({ armed: false, since: 0 })
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const data = setup?.data
  useEffect(() => setArmed(false), [data?.plan_digest])
  useEffect(() => {
    if (!restart.since) return undefined
    if (data?.ok === true && data.active === true && data.ready === true) {
      setRestart({ armed: false, since: 0 })
      setNote({ tone: 'ok', text: t('wa.setupRestartReady') })
      onComplete?.()
      return undefined
    }
    if (Date.now() - restart.since >= RESTART_WAIT_MS) {
      setRestart({ armed: false, since: 0 })
      setNote({ tone: 'bad', text: t('wa.setupRestartLate') })
      return undefined
    }
    const id = setTimeout(() => { if (alive.current && scope?.matches()) onReload?.() }, RESTART_POLL_MS)
    return () => clearTimeout(id)
  }, [restart.since, data, setup])
  if (!setup || (data?.ok === true && data.active === true && data.ready === true && !note)) return null
  if (setup.error || data?.ok === false) {
    return jsx(Failure, { t, text: t('wa.setupReadFailed'), detail: setup.error
      || txReason(data.reason, data.reason_source, t)?.text || t('wa.candFailed') }, 'setup-error')
  }
  if (!data) return null
  const turnOn = async () => {
    if (busy || !scope?.matches() || typeof data.plan_digest !== 'string') return
    setBusy(true)
    setNote(null)
    try {
      const result = await api.ownerActivate(data.plan_digest) || {}
      if (!alive.current || !scope?.matches()) return
      setNote(result.ok ? { tone: 'ok', text: t('wa.setupDone') }
        : { tone: 'bad', text: txReason(result.reason, result.reason_source, t)?.text || t('wa.candFailed') })
      if (result.ok) onComplete?.()
    } catch (error) {
      if (alive.current && scope?.matches()) setNote({ tone: 'bad', text: errText(error) })
    } finally {
      if (alive.current) { setBusy(false); setArmed(false) }
    }
  }
  const restartService = async () => {
    if (restart.since || !scope?.matches()) return
    setNote(null)
    try {
      const result = await host.restartGateway()
      if (!alive.current || !scope?.matches()) return
      if (result && result.ok === false) {
        setRestart({ armed: false, since: 0 })
        setNote({ tone: 'bad', text: result.error || result.message || t('wa.candFailed') })
        return
      }
      setRestart({ armed: false, since: Date.now() })
    } catch (error) {
      if (alive.current && scope?.matches()) {
        setRestart({ armed: false, since: 0 })
        setNote({ tone: 'bad', text: errText(error) })
      }
    }
  }
  const restartRow = jsxs('div', { className: 'wa-confirm', children: [
    jsx('p', { className: 'wa-confirm-text', children: restart.since ? t('wa.setupRestarting') : t('wa.setupRestartWhat') }, 'what'),
    jsx('div', { className: 'wa-confirm-row', children: restart.armed ? [
      jsx(Button, { onClick: () => setRestart({ armed: false, since: 0 }), size: 'sm', variant: 'outline',
        children: t('wa.jobCancel') }, 'cancel'),
      jsx(Button, { onClick: restartService, size: 'sm', variant: 'default', children: t('wa.setupRestartConfirm') }, 'confirm')
    ] : jsx(Button, { loading: !!restart.since, disabled: !!restart.since, size: 'sm', variant: 'default',
      onClick: () => { setNote(null); setRestart({ armed: true, since: 0 }) }, children: t('wa.setupRestartArm') }, 'arm') }, 'row')
  ] }, 'restart')
  const pending = data.active === true
  return jsxs('section', { 'data-owner-setup': pending ? 'restart' : 'off', className: 'wa-body', children: [
    jsx('h2', { children: pending ? t('wa.setupPendingTitle') : t('wa.setupOffTitle') }, 'title'),
    note ? jsx('div', { className: `wa-msg wa-${note.tone}`, role: 'status', children: note.text }, 'note') : null,
    pending ? (data.ready === true ? null : jsxs('div', { children: [
      note ? null : jsx('p', { className: 'wa-confirm-text', children: t('wa.setupPending') }, 'pending'),
      restartRow
    ] }, 'pending'))
      : jsxs('div', { className: 'wa-confirm', children: [
        jsx('p', { className: 'wa-confirm-text',
          children: data.code_changed ? t('wa.setupChanged') : t('wa.setupOff') }, 'why'),
      jsxs('ul', { className: 'wa-confirm-text', children: [
        jsx('li', { children: t('wa.setupOwner', data.owner) }, 'owner'),
        jsx('li', { children: t('wa.setupJob', data.job?.name, data.job?.schedule) }, 'job'),
        jsx('li', { children: t('wa.setupRestart') }, 'restart')
      ] }, 'changes'),
      jsx('div', { className: 'wa-confirm-row', children: armed ? [
        jsx(Button, { disabled: busy, onClick: () => setArmed(false), size: 'sm', variant: 'outline',
          children: t('wa.jobCancel') }, 'cancel'),
        jsx(Button, { loading: busy, disabled: busy, onClick: turnOn, size: 'sm', variant: 'default',
          children: t('wa.setupConfirm') }, 'confirm')
      ] : jsx(Button, { disabled: busy, onClick: () => { setNote(null); setArmed(true) }, size: 'sm', variant: 'default',
        children: t('wa.setupTurnOn') }, 'arm') }, 'row')
    ] }, 'off')
  ] }, 'setup')
}




function idFilePath(root) {
  const clean = String(root || '').replace(/[\\/]+$/, '')
  if (!clean) return undefined
  const sep = clean.includes('\\') ? '\\' : '/'
  return `${clean}${sep}.llm-wiki${sep}project.json`
}






const LINE_HUES = ['var(--ui-accent)', 'var(--ui-green)', 'var(--ui-purple)', 'var(--ui-cyan)']
const LINE_ORDER = ['hermes', 'codex', 'claude', 'antigravity']
const LINE_NAMES = { hermes: 'Hermes', codex: 'Codex', claude: 'Claude Code', antigravity: 'Antigravity' }
const MORNING_ROLES = ['watchdog', 'ingest_watch', 'autocommit']
const ENGINE_ASK = ['missing', 'existing_unverified', 'prepared', 'applying', 'recovery_required']
const ENGINE_UPDATABLE = ['installed_paused', 'installed_with_existing_jobs']
const engineUpdate = data => (data?.ok === true && ENGINE_UPDATABLE.includes(data.state)
  && engineHex(data.current_revision, 40) && engineHex(data.selected_revision, 40)
  && data.current_revision !== data.selected_revision
  ? { current: data.current_revision.slice(0, 7), selected: data.selected_revision.slice(0, 7) } : null)
const HARVEST_ROLE = 'session_harvest'
const HARVEST_LIVE_MS = 3 * 3600 * 1000
const RUN_STORE_LIMIT = 3

const lineName = row => (Object.hasOwn(LINE_NAMES, row.id) ? LINE_NAMES[row.id] : String(row.id || '—'))
const lineHue = (row, index) => LINE_HUES[LINE_ORDER.includes(row.id) ? LINE_ORDER.indexOf(row.id)
  : index % LINE_HUES.length]
const LIVE_LINE = ['ok', 'run']
const lineUnread = (row, last) => row.enabled && row.found && String(last?.agents?.[row.id] || '').startsWith('UNREADABLE')
const lineState = (row, running, last) => (!row.found ? 'missing' : !row.enabled ? 'off' : running ? 'run'
  : lineUnread(row, last) ? 'unread' : 'ok')
const harvestOutcome = (data, latest, running) => {
  if (!data || data.ok !== true || running || !latest || ACTIVE_STATUS.includes(latest.status)) return null
  const last = data.last_run
  if (!last) return null
  const finished = last.execution_id === latest.id || stampAt(latest) > (Date.parse(last.created || '') || 0)
  return finished && !(last.execution_id === latest.id && last.committed === true) ? 'stopped' : null
}
const capFirst = text => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text)
const shortText = (text, size = 150) => {
  const line = String(text || '').trim().split(/\r?\n/)[0].trim()
  return line.length > size ? `${line.slice(0, size - 1)}…` : line
}
const hourOf = iso => isoParts(iso)?.time || ''
const stampAt = run => Date.parse(run?.at || '') || 0
const refusal = (t, data) => (data && data.ok === false
  ? String(data.error || txReason(data.reason, data.reason_source, t)?.text || '') : '')
const listText = (t, names) => (names.length > 1
  ? t('wa.metroAnd', names.slice(0, -1).join(', '), names[names.length - 1]) : names.join(''))
const morningName = (t, role) => (role === 'watchdog' ? t('wa.metroDailyCheck')
  : role === 'ingest_watch' ? t('wa.metroNewSources') : t('wa.metroSaving'))
const morningDoes = (t, role) => (role === 'watchdog' ? t('wa.metroDailyCheckDoes')
  : role === 'ingest_watch' ? t('wa.metroNewSourcesDoes') : t('wa.metroSavingDoes'))

function untilText(t, iso, now = Date.now()) {
  const at = isoParts(iso)?.at
  if (!at || at < now) return ''
  const minutes = Math.max(1, Math.round((at - now) / 60000))
  return minutes < 60 ? t('wa.metroInMin', minutes) : t('wa.metroIn', Math.floor(minutes / 60), two(minutes % 60))
}

function useMetroReads(checks) {
  const auto = usePanelPolling(api.automation, 60000)
  const jobs = usePanelPolling(api.jobs, 60000)
  const harvest = usePolling(api.harvestStatus, 60000)
  const runs = usePolling(() => healthApi.jobs('24h'), 60000)
  const store = usePolling(() => api.runs(RUN_STORE_LIMIT), 60000)
  const watch = usePolling(() => (checks ? healthApi.watchdog() : Promise.resolve({ ok: true, runs: [] })),
    checks ? 60000 : 0, [checks])
  const engine = usePolling(api.engineStatus, 60000)
  const folio = useFolioPolling()
  const map = usePolling(api.wikiMap, 300000)
  const cands = { ...folio.candidates, busy: folio.busy, refresh: folio.refresh }
  const reads = [auto, jobs, harvest, runs, store, watch, engine, folio]
  const busy = reads.some(read => read.busy)
  const refresh = () => [...reads, map].filter(read => read !== engine).forEach(read => read.refresh?.())
  return { auto, jobs, harvest, runs, store, watch, engine, folio, cands, map, busy, refresh }
}

function metroFailures(t, reads, projectOk) {
  const { auto, jobs, harvest, runs, store, watch, engine, folio } = reads
  const list = []
  const add = (what, error) => { if (error) list.push({ what, error: String(error) }) }
  add('', jobs.error || refusal(t, jobs.data))
  add(t('wa.metroWhatLines'), harvest.error)
  add(t('wa.metroWhatSettings'), auto.error || refusal(t, auto.data))
  add(t('wa.metroWhatDrafts'), folio.candidates?.error || refusal(t, folio.candidates?.data)
    || (projectOk ? folio.error : ''))
  add(t('wa.metroWhatRuns'), runs.error)
  add(t('wa.metroWhatRuns'), store.error || refusal(t, store.data) || store.data?.error)
  add(t('wa.metroWhatChecks'), watch.error)
  add(t('wa.metroWhatEngine'), engine.error || refusal(t, engine.data))
  return list
}

function harvestModel(t, reads, lines) {
  const { jobs, runs, store, harvest: status } = reads
  const known = Boolean(jobs.data) && jobs.data.ok !== false && !jobs.error
  const roles = known ? jobs.data.roles || [] : []
  const role = roles.find(row => row.role === HARVEST_ROLE) || null
  const history = (runs.data?.runs || []).filter(run => role?.id && run.job_id === role.id)
    .sort((a, b) => stampAt(b) - stampAt(a))
  const stored = store.error || store.data?.ok === false ? null
    : (store.data?.jobs || []).find(row => row.role === HARVEST_ROLE)?.runs?.[0] || null
  const fresh = run => Boolean(run) && ACTIVE_STATUS.includes(run.status)
    && Date.now() - stampAt(run) < HARVEST_LIVE_MS
  const live = Boolean(role?.live)
  const running = live && role.target?.impl_ok !== false && (fresh(history[0]) || fresh(stored))
  const active = running ? (fresh(history[0]) ? history[0] : stored) : null
  const latest = active || history[0] || null
  const recorded = live && !running && (role.last_status === 'error' || latest?.status === 'failed')
  const outcome = live && !recorded ? harvestOutcome(status?.data, history[0] || null, running) : null
  const failed = recorded || outcome === 'stopped'
  const stopsAll = status?.data?.ok === true && status.data.last_run_supported === false
  const blocked = live && !running && stopsAll && lines.some(line => line.state === 'missing' && line.row.enabled)
  const paused = live && role.state === 'paused'
  const stoppedAt = latest?.finished_at || role?.last_run_at || latest?.at || ''
  const cause = recorded ? String(role.last_error || latest?.error_preview || '')
    : outcome === 'stopped' ? (status?.data?.last_run?.stop_reason?.detail || t('wa.metroHvNotFinished')) : ''
  const feeding = lines.filter(line => line.row.found && line.row.enabled && line.state !== 'unread').length
  const does = lines.length && feeding < lines.length ? t('wa.metroHvReads', feeding, lines.length)
    : t('wa.metroHvDoes')
  const pill = (glyph, tone, text) => ({ glyph, tone, text })
  const station = !known ? { state: 'bad', line1: t('wa.metroNotReported'), line2: t('wa.metroNoTimetable') }
    : !live ? { state: 'bad', line1: t('wa.metroHvNoJob'), line2: t('wa.metroHvSetUp') }
      : running ? { state: 'run', pill: pill('sync', 'ask', t('wa.metroCollecting')), line1: t('wa.metroHvReading'),
        line2: t('wa.metroHvStarted', hourOf(active.at) || '—', relText(t, active.at)) }
        : failed ? { state: 'bad', pill: pill('error', 'bad', t('wa.metroFailedPill')),
          line1: t('wa.metroHvStopped', hourOf(stoppedAt) || '—'), line2: t('wa.metroHvLastFailed') }
          : paused ? { state: 'paused', pill: pill('debug-pause', 'warn', t('wa.metroPausedShort')),
            line1: does, line2: t('wa.metroHvPaused') }
            : blocked ? { state: 'bad', line1: t('wa.metroHvBlocked'), line2: t('wa.metroSeeAlert') }
            : role.target?.impl_ok === false ? { state: 'bad', line1: t('wa.metroHvMissingTarget'),
              line2: t('wa.metroSeeAlert') }
              : role.target?.root_ok === false ? { state: 'bad', line1: t('wa.metroHvNotVerified'),
                line2: t('wa.metroSeeAlert') }
                : !role.target?.ok ? { state: 'bad', line1: t('wa.metroHvCannotRun'), line2: t('wa.metroSeeAlert') }
              : { state: 'ok', pill: role.next_run_at ? pill('clock', 'ask', t('wa.metroNext', hourOf(role.next_run_at)))
                : null, line1: does, line2: untilText(t, role.next_run_at) || t('wa.metroHvNoNext') }
  const engineRun = status?.data?.ok === true ? status.data.last_run : null
  const cost = !running && engineRun && history[0] && engineRun.execution_id === history[0].id
    && typeof engineRun.cost_usd === 'number' ? engineRun.cost_usd : null
  return { known, roles, role, latest, running, failed, paused, stoppedAt, cause, station, stopsAll, cost }
}

function reviewModel(t, reads, projectOk, running) {
  const { auto, folio } = reads
  const data = folio.candidates?.data
  const unread = Boolean(folio.candidates?.error || data?.ok === false || (projectOk && folio.error))
  const count = data && data.ok !== false && !folio.candidates?.error ? (data.candidates || []).length : null
  const setup = folio.setup?.data
  const ownerNeeded = setup?.ok === true && !(setup.active === true && setup.ready === true)
  const second = ownerNeeded ? t('wa.metroSetupNeeded') : running ? t('wa.metroArrive') : t('wa.metroDecide')
  const station = unread ? { state: 'bad', line1: t('wa.metroDraftsUnread'), line2: t('wa.metroSeeAlert') }
    : auto.data && !projectOk ? { state: 'warn', line1: t('wa.metroNoFolder'), line2: t('wa.metroChooseFolder') }
      : count == null ? { state: 'ok', line1: t('wa.metroReading'), line2: t('wa.metroDecide') }
        : count ? { state: 'ask', pill: { glyph: 'inbox', tone: 'ask', text: t('wa.metroWaitingPill', count) },
          line1: t('wa.metroDraftsWaiting', count), line2: second }
          : { state: ownerNeeded ? 'warn' : 'ok', line1: t('wa.metroDraftsWaiting', 0), line2: second }
  return { count, unread, ownerNeeded, station }
}

function sameSince(watch) {
  const list = (watch.data?.runs || []).slice().sort((a, b) => (Number(b.ts) || 0) - (Number(a.ts) || 0))
  const key = run => JSON.stringify((run.findings || []).slice().sort())
  const first = list[0] ? key(list[0]) : ''
  let oldest = null
  for (const run of list) {
    if (key(run) !== first) break
    oldest = run
  }
  if (!oldest || oldest === list[0]) return ''
  const day = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(oldest.date || ''))
  return day ? `${day[3]}.${day[2]}` : ''
}

function wikiModel(t, reads, roles) {
  const { auto, runs, watch } = reads
  const pages = auto.data?.settings?.project?.pages
  const watchRole = roles.find(row => row.role === 'watchdog')
  const checks = (runs.data?.runs || []).filter(run => watchRole?.id && run.job_id === watchRole.id && run.at
    && !ACTIVE_STATUS.includes(run.status))
  const check = checks.sort((a, b) => stampAt(b) - stampAt(a))[0] || null
  const logged = (watch.data?.runs || []).slice().sort((a, b) => (Number(b.ts) || 0) - (Number(a.ts) || 0))[0] || null
  const findings = check ? check.findings || [] : logged?.items || []
  const checkedAt = check?.at || ''
  const since = findings.length ? sameSince(watch) : ''
  const morning = MORNING_ROLES.map(role => roles.find(row => row.role === role) || { role, live: false })
  const failing = morning.filter(row => row.live && row.last_status === 'error'
    && !(row.role === 'watchdog' && findings.length))
  const line1 = typeof pages === 'number' ? t('wa.metroPages', pages) : t('wa.metroPagesUnknown')
  const station = runs.error || watch.error ? { state: 'bad', line1, line2: t('wa.metroChecksUnread') }
    : failing.length ? { state: 'bad', line1, line2: t('wa.metroJobFailed', morningName(t, failing[0].role)) }
      : findings.length ? { state: 'warn', line1, line2: t('wa.metroProblems', findings.length) }
        : !runs.data ? { state: 'ok', line1, line2: t('wa.metroReading') }
          : { state: 'ok', line1, line2: check || logged ? t('wa.metroNoProblems') : t('wa.metroNoCheck') }
  return { pages, check, logged, checkedAt, findings, since, morning, failing, station }
}

function engineHeading(t, state) {
  return state === 'missing' ? t('wa.engineBannerMissing') : state === 'update' ? t('wa.engineBannerUpdate')
    : ['applying', 'recovery_required'].includes(state) ? t('wa.engineBannerRecovery') : t('wa.engineBannerUnverified')
}

function metroAlert(t, parts) {
  const { failures, engineState, update, auto, projectOk, review, harvest, lines, wiki, pending } = parts
  const settings = { label: t('wa.metroOpenSettings'), open: 'settings' }
  const install = { label: t('wa.metroOpenSettings'), open: 'settings', jump: 'install' }
  if (failures.length) {
    const [first, ...rest] = failures
    return { key: 'read-failed', tone: 'bad', glyph: 'error', action: { label: t('wa.metroTryAgain'), retry: true },
      heading: first.what ? t('wa.metroReadFailed', first.what) : t('wa.metroReadTimetable'),
      text: [t('wa.metroUntouched'), rest.length ? t('wa.metroReadMore', rest.length) : ''].filter(Boolean).join(' '),
      raw: [first, ...rest].map(row => String(row.error || '')).filter(Boolean).join('\n') }
  }
  if (ENGINE_ASK.includes(engineState)) {
    return { key: 'engine', tone: 'warn', glyph: 'tools', action: install, text: t('wa.metroEngineText'),
      banner: engineState, heading: engineHeading(t, engineState) }
  }
  if (update) {
    return { key: 'engine', tone: 'ask', glyph: 'tools', action: install, banner: 'update',
      heading: engineHeading(t, 'update'), text: t('wa.metroEngineUpdateText', update.current, update.selected) }
  }
  if (auto.data && !projectOk) {
    return { key: 'engine', tone: 'warn', glyph: 'folder', heading: t('wa.metroFolderTitle'),
      text: t('wa.metroFolderText'), action: settings }
  }
  if (review.ownerNeeded) {
    return { key: 'engine', tone: 'warn', glyph: 'shield', heading: t('wa.metroOwnerTitle'),
      text: t('wa.metroOwnerText'), action: { label: t('wa.metroOpenReview'), open: 'review' } }
  }
  const showHarvest = { label: t('wa.metroShowHarvest'), open: 'harvest' }
  if (harvest.failed) {
    return { key: 'harvest-failed', tone: 'bad', glyph: 'error',
      action: { label: t('wa.metroShowError'), open: 'harvest' },
      heading: t('wa.metroHvFailTitle', hourOf(harvest.stoppedAt) || '—'),
      text: harvest.cause ? t('wa.metroHvFailReason', shortText(harvest.cause)) : t('wa.metroHvFailNoReason') }
  }
  const broken = harvest.roles.find(row => row.live && row.state !== 'paused' && !row.target?.ok)
  if (broken) {
    return { key: 'job-broken', tone: 'bad', glyph: 'warning', heading: t('wa.metroJobCannotRun', broken.name),
      text: broken.target?.root_ok ? t('wa.jobScriptMissing', broken.target?.impl || '') : t('wa.jobRootMissing'),
      action: broken.role === HARVEST_ROLE ? showHarvest : settings }
  }
  const absent = harvest.roles.find(row => !row.live)
  if (absent) {
    return { key: 'job-broken', tone: 'bad', glyph: 'warning', heading: t('wa.metroJobMissing', absent.name),
      text: t('wa.metroJobMissingText'), action: settings }
  }
  const unreadAll = lines.filter(line => line.state === 'unread')
  if (unreadAll.length) {
    const others = lines.filter(line => !unreadAll.includes(line) && line.row.found && line.row.enabled).length
    const names = listText(t, unreadAll.map(line => line.name))
    return { key: 'job-broken', tone: 'warn', glyph: 'warning',
      heading: unreadAll.length > 1 ? t('wa.metroLinesUnreadTitle', names) : t('wa.metroLineUnreadTitle', unreadAll[0].name),
      text: t('wa.metroLineUnreadText', others), raw: unreadAll.map(line => `${line.id}: ${line.report}`).join('\n'),
      action: { label: t('wa.metroShowLine'), open: `line:${unreadAll[0].id}` } }
  }
  const closedAll = harvest.stopsAll ? lines.filter(line => line.state === 'missing' && line.row.enabled) : []
  const closed = closedAll[0]
  if (closed) {
    const names = listText(t, closedAll.map(line => line.name))
    return { key: 'job-broken', tone: 'bad', glyph: 'folder',
      heading: closedAll.length > 1 ? t('wa.metroLinesClosed', names) : t('wa.metroLineClosed', closed.name),
      text: t('wa.metroLinesStopAll'), action: install }
  }
  if (review.count) {
    return { key: 'drafts', tone: 'ask', glyph: 'inbox', heading: t('wa.metroDraftsTitle', review.count),
      text: t('wa.metroDraftsText'), action: { label: t('wa.metroReviewDrafts'), open: 'review' } }
  }
  if (wiki.failing.length) {
    const row = wiki.failing[0]
    return { key: 'problems', tone: 'bad', glyph: 'error', heading: t('wa.metroJobFailed', morningName(t, row.role)),
      text: row.last_error ? shortText(row.last_error) : t('wa.metroHvFailNoReason'),
      action: { label: t('wa.metroShowWiki'), open: 'wiki' } }
  }
  if (wiki.findings.length) {
    const named = wiki.findings.slice(0, 2).map(f => findingShort(f, t))
    return { key: 'problems', tone: 'warn', glyph: 'warning',
      heading: wiki.since ? t('wa.metroProblemsSince', wiki.findings.length, wiki.since)
        : t('wa.metroProblemsTitle', wiki.findings.length),
      text: capitalFirst(t('wa.metroProblemsMore', named.join(', '), wiki.findings.length - named.length)),
      action: { label: t('wa.metroShowProblems', wiki.findings.length), open: 'wiki' } }
  }
  const resting = harvest.roles.find(row => row.live && row.state === 'paused')
  if (resting) {
    return { key: 'paused', tone: 'warn', glyph: 'debug-pause', heading: t('wa.metroPausedTitle', resting.name),
      text: t('wa.metroPausedText'), action: resting.role === HARVEST_ROLE ? showHarvest : settings }
  }
  if (harvest.running) {
    return { key: 'running', tone: 'ask', glyph: 'sync', heading: t('wa.metroRunningTitle'),
      text: t('wa.metroRunningText'), action: null }
  }
  if (pending) return null
  const next = harvest.role?.next_run_at ? whenText(t, harvest.role.next_run_at) : ''
  return { key: 'good', tone: 'ok', glyph: 'pass', heading: t('wa.metroGoodTitle'),
    text: next ? t('wa.metroGoodNext', next) : t('wa.metroGoodText'), action: null }
}

function metroModel(t, reads) {
  const { auto, jobs, harvest: status, runs, watch, engine, folio } = reads
  const loading = [auto, jobs, status].some(read => !read.data && !read.error)
  const projectOk = auto.data?.settings?.project?.ok === true
  const failures = metroFailures(t, reads, projectOk)
  const agents = status.data?.agents || []
  const last = status.data?.last_run || null
  const draft = agents.map((row, index) => ({ row, id: String(row.id), name: lineName(row),
    hue: lineHue(row, index), state: lineState(row, false, last), report: String(last?.agents?.[row.id] || '') }))
  const harvest = harvestModel(t, reads, draft)
  const lines = draft.map(line => ({ ...line, state: lineState(line.row, harvest.running, last) }))
  const review = reviewModel(t, reads, projectOk, harvest.running)
  const wiki = wikiModel(t, reads, harvest.roles)
  const engineState = engine.data?.ok === true ? engine.data.state : null
  const update = engineUpdate(engine.data)
  const pending = [runs, watch, engine].some(read => !read.data && !read.error)
    || (!folio.candidates && !folio.error)
  const alert = metroAlert(t, { failures, engineState, update, auto, projectOk, review, harvest, lines, wiki,
    pending })
  const segs = [harvest.station.state === 'bad' ? 'off' : harvest.running ? 'dim' : 'on',
    harvest.running || ['ask', 'bad'].includes(review.station.state) ? 'dim' : 'on']
  const stations = [
    { id: 'harvest', name: t('wa.metroHarvest'), model: harvest.station },
    { id: 'review', name: t('wa.metroReview'), model: review.station },
    { id: 'wiki', name: t('wa.metroWiki'), model: wiki.station }
  ]
  const engineAsk = ENGINE_ASK.includes(engineState) ? engineState : update ? 'update' : null
  return { loading, failures, lines, harvest, review, wiki, alert, segs, stations, engineAsk, update }
}

function metroWires(root) {
  const box = root.getBoundingClientRect()
  const at = el => {
    const r = el.getBoundingClientRect()
    return { l: r.left - box.left, r: r.right - box.left, t: r.top - box.top, b: r.bottom - box.top,
      x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2, w: r.width }
  }
  const stops = [...root.querySelectorAll('[data-wa-station] .wa-metro-stop')].map(at)
  const lines = [...root.querySelectorAll('[data-wa-line]')]
  if (stops.length < 3 || !stops[0].w) return { dir: root.dataset.dir || 'h', paths: [] }
  const dir = stops[1].t >= stops[0].b ? 'v' : 'h'
  const segs = String(root.dataset.segs || '').split(',')
  const n = v => Math.round(v * 10) / 10
  const first = stops[0]
  const paths = lines.map((line, index) => {
    const dot = at(line.querySelector('.wa-metro-line-dot'))
    const meta = { key: `line-${line.dataset.waLine}`, kind: 'line', state: line.dataset.state || 'ok',
      hue: line.style.getPropertyValue('--wa-hue') }
    if (dir === 'h') {
      const start = at(line.querySelector('.wa-metro-line-text')).r + 2
      const join = Math.max(start + 24, first.x - 110)
      const mid = start + (join - start) / 2
      return { ...meta, d: `M${n(start)} ${n(dot.y)} C${n(mid)} ${n(dot.y)} ${n(mid)} ${n(first.y)} `
        + `${n(join)} ${n(first.y)} L${n(first.l + 1)} ${n(first.y)}` }
    }
    const lane = first.x - 9 + index * 6
    return { ...meta, d: `M${n(dot.l - 3)} ${n(dot.y)} L${n(lane + 8)} ${n(dot.y)} Q${n(lane)} ${n(dot.y)} `
      + `${n(lane)} ${n(dot.y + 8)} L${n(lane)} ${n(first.t - 2)}` }
  }).sort((a, b) => Number(LIVE_LINE.includes(a.state)) - Number(LIVE_LINE.includes(b.state)))
  for (let i = 0; i < stops.length - 1; i += 1) {
    const a = stops[i]
    const b = stops[i + 1]
    paths.push({ key: `seg-${i}`, kind: 'seg', state: segs[i] || 'on', hue: '',
      d: dir === 'h' ? `M${n(a.r)} ${n(a.y)} L${n(b.l)} ${n(b.y)}` : `M${n(a.x)} ${n(a.b)} L${n(b.x)} ${n(b.t)}` })
  }
  return { dir, paths }
}

function useMetroWires(ref, shape) {
  const [wires, setWires] = useState({ dir: 'h', paths: [] })
  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return undefined
    const measure = () => {
      const next = metroWires(root)
      setWires(previous => (JSON.stringify(previous) === JSON.stringify(next) ? previous : next))
    }
    measure()
    const watcher = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null
    if (watcher) [root, ...root.querySelectorAll('[data-wa-station],[data-wa-line]')].forEach(el => watcher.observe(el))
    return () => watcher?.disconnect()
  }, [shape])
  return wires
}

function MetroPill({ pill }) {
  if (!pill) return jsx('span', { className: 'wa-metro-pill', 'data-empty': '1', 'aria-hidden': true }, 'pill')
  return jsxs('span', { className: 'wa-metro-pill', 'data-tone': pill.tone, children: [
    icon(pill.glyph),
    jsx('span', { children: pill.text }, 'text')
  ] }, 'pill')
}

function MetroStation({ station, open, onToggle }) {
  const { id, name, model } = station
  return jsxs('button', {
    type: 'button', className: 'wa-metro-station', 'data-wa-station': id, 'data-state': model.state,
    'aria-pressed': open, 'aria-label': [name, model.line1, model.line2].filter(Boolean).join(' · '),
    onClick: onToggle,
    children: [
      jsx(MetroPill, { pill: model.pill }, 'pill'),
      jsx('span', { className: 'wa-metro-stop', 'aria-hidden': true }, 'stop'),
      jsxs('span', { className: 'wa-metro-copy', children: [
        jsx('span', { className: 'wa-metro-name', children: name }, 'name'),
        jsx('span', { className: 'wa-metro-text', children: model.line1 }, 'line1'),
        model.line2 ? jsx('span', { className: 'wa-metro-text', children: model.line2 }, 'line2') : null
      ] }, 'copy')
    ]
  }, id)
}

function MetroLine({ t, line, open, onToggle }) {
  const note = line.state === 'missing' ? t('wa.metroLineMissing') : line.state === 'off' ? t('wa.metroLineOff')
    : line.state === 'run' ? t('wa.metroLineReading') : line.state === 'unread' ? t('wa.metroLineUnread') : null
  return jsxs('button', {
    type: 'button', className: 'wa-metro-line', 'data-wa-line': line.id, 'data-state': line.state,
    'aria-pressed': open, 'aria-label': `${line.name} · ${note || t('wa.metroCollecting')}`,
    style: { '--wa-hue': line.hue }, onClick: onToggle,
    children: [
      jsx('span', { className: 'wa-metro-line-dot', 'aria-hidden': true }, 'dot'),
      jsxs('span', { className: 'wa-metro-line-text', children: [
        jsx('span', { className: 'wa-metro-line-name', children: line.name }, 'name'),
        note ? jsx('span', { className: 'wa-metro-line-note', children: note }, 'note') : null
      ] }, 'text')
    ]
  }, line.id)
}

function MetroTitle({ t, sub }) {
  return jsxs('h2', { className: 'wa-metro-title', children: [
    jsx('span', { children: t('wa.metroLine') }, 'name'),
    jsx('span', { className: 'wa-metro-subtitle', children: sub }, 'sub')
  ] }, 'title')
}

function MetroMap({ t, model, reads, open, toggle }) {
  const mapRef = useRef(null)
  const shape = JSON.stringify([model.segs, model.lines.map(line => [line.id, line.state]),
    model.stations.map(row => [row.id, row.model.state, row.model.line1, row.model.line2, row.model.pill?.text])])
  const wires = useMetroWires(mapRef, shape)
  const timetable = model.harvest.known
  if (!timetable && model.alert?.key === 'read-failed') {
    return jsx('section', { ref: mapRef, className: 'wa-metro-map', 'data-unread': '1', 'aria-label': t('wa.metroLine'),
      children: jsx(MetroTitle, { t, sub: t('wa.metroNoTimetable') }, 'title') }, 'map')
  }
  const lines = model.lines.length ? model.lines.map(line => jsx(MetroLine, { t, line,
    open: open === `line:${line.id}`, onToggle: () => toggle(`line:${line.id}`) }, line.id))
    : jsx('span', { className: 'wa-metro-line-note', children: reads.harvest.error ? t('wa.metroLinesUnread')
      : t('wa.metroNoLines') }, 'none')
  return jsxs('section', {
    ref: mapRef, className: 'wa-metro-map', 'data-dir': wires.dir, 'data-segs': model.segs.join(','),
    'aria-label': t('wa.metroLine'),
    children: [
      jsx('svg', { className: 'wa-metro-wires', 'aria-hidden': true, focusable: 'false',
        children: wires.paths.map(path => jsx('path', {
          className: 'wa-metro-wire', d: path.d, 'data-kind': path.kind,
          'data-state': timetable ? path.state : 'unknown',
          style: path.hue ? { '--wa-hue': path.hue } : undefined
        }, path.key)) }, 'wires'),
      jsx(MetroTitle, { t, sub: timetable ? t('wa.metroLineSub') : t('wa.metroNoTimetable') }, 'title'),
      jsxs('div', { className: 'wa-metro-grid', children: [
        jsxs('div', { className: 'wa-metro-lines', children: [
          jsx('span', { className: 'wa-metro-group', children: t('wa.metroConversations') }, 'group'),
          ...[].concat(lines)
        ] }, 'lines'),
        jsx('div', { className: 'wa-metro-stations', children: model.stations.map(station => jsx(MetroStation, {
          station, open: open === station.id, onToggle: () => toggle(station.id)
        }, station.id)) }, 'stations')
      ] }, 'grid')
    ]
  }, 'map')
}

function MetroSkeleton({ t }) {
  const bone = (shape, key) => jsx('span', { className: 'wa-metro-bone', 'data-shape': shape }, key)
  return jsxs('section', { className: 'wa-metro-map wa-metro-skeleton', 'aria-busy': true,
    'aria-label': t('wa.metroReadingTimetable'), children: [
      jsx(MetroTitle, { t, sub: t('wa.metroReadingTimetable') }, 'title'),
      jsxs('div', { className: 'wa-metro-grid', children: [
        jsx('div', { className: 'wa-metro-lines', children: ['a', 'b', 'c', 'd'].map(id => bone('line', id)) },
          'lines'),
        jsx('div', { className: 'wa-metro-stations', children: ['h', 'r', 'w'].map(id => jsxs('span', {
          className: 'wa-metro-bones', children: [bone('stop', 'stop'), bone('name', 'name'), bone('text', 'text')]
        }, id)) }, 'stations')
      ] }, 'grid')
    ] }, 'skeleton')
}

function MetroBar({ t, alert, onAct }) {
  return jsxs('div', {
    className: 'wa-metro-bar', 'data-tone': alert.tone, 'data-alert': alert.key,
    'data-engine-banner': alert.banner || undefined,
    role: alert.tone === 'bad' ? 'alert' : 'status',
    children: [
      jsx('span', { className: 'wa-metro-bar-icon', children: icon(alert.glyph) }, 'icon'),
      jsxs('div', { className: 'wa-metro-bar-copy', children: [
        jsx('strong', { className: 'wa-metro-bar-head', children: alert.heading }, 'heading'),
        alert.text ? jsx('span', { className: 'wa-metro-bar-text', children: alert.text }, 'text') : null,
        alert.raw ? jsxs('details', { className: 'wa-metro-raw wa-metro-bar-raw', children: [
          jsx('summary', { children: t('wa.metroShowError') }, 'summary'),
          jsx(PanelBlock, { className: 'wa-mono', children: alert.raw }, 'raw')
        ] }, 'raw') : null
      ] }, 'copy'),
      alert.action ? jsx(Button, { className: 'wa-metro-bar-act', variant: 'outline',
        onClick: () => onAct(alert.action), children: alert.action.label }, 'act') : null
    ]
  }, alert.key)
}

function EngineNotice({ t, state, onAct }) {
  return jsxs('div', { className: 'wa-metro-notice', role: 'status', 'data-engine-banner': state, children: [
    icon('tools'),
    jsx('span', { className: 'wa-metro-notice-text', children: engineHeading(t, state) }, 'text'),
    jsx(Button, { size: 'sm', variant: 'outline', onClick: onAct, children: t('wa.metroOpenSettings') }, 'open')
  ] }, 'engine-notice')
}

function notchTarget(root, id) {
  if (!root) return null
  if (id.startsWith('line:')) {
    return [...root.querySelectorAll('[data-wa-line]')].find(el => el.dataset.waLine === id.slice(5)) || null
  }
  return [...root.querySelectorAll('[data-wa-station]')].find(el => el.dataset.waStation === id) || null
}

function useNotch(ref, id, folded) {
  const [notch, setNotch] = useState(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || folded) return undefined
    const root = el.closest('.wa-metro')
    const measure = () => {
      const target = notchTarget(root, id)
      const box = el.getBoundingClientRect()
      let prev = el.previousElementSibling
      while (prev && !prev.classList.contains('wa-metro-map') && prev.matches('.wa-metro-bar, .wa-metro-notice')) {
        prev = prev.previousElementSibling
      }
      const after = Boolean(prev?.classList.contains('wa-metro-map'))
      if (!target || !after || !box.width) { setNotch(null); return }
      const spot = target.querySelector('.wa-metro-stop, .wa-metro-line-dot') || target
      const at = spot.getBoundingClientRect()
      const x = Math.round(at.left + at.width / 2 - box.left)
      setNotch(x > 20 && x < box.width - 20 ? x : null)
    }
    measure()
    const watcher = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null
    if (watcher && root) watcher.observe(root)
    return () => watcher?.disconnect()
  }, [id, folded])
  return notch
}

const GLOBE = { gold: Math.PI * (3 - Math.sqrt(5)), tilt: 0.3, gap: 0.035, turn: 0.008, lines: 12, rings: 3, recent: 7,
  angles: [-0.42, -0.08, 0.26, 0.64] }
const GLOBE_BANDS = ['concepts', 'entities', 'sources', 'other']

function globeModel(map) {
  if (!map) return null
  const pages = map.pages || []
  const missing = map.missing || []
  const total = typeof map.missing_total === 'number' ? map.missing_total : missing.length
  const group = new Map()
  missing.forEach((row, index) => (row.holders || []).forEach(id => {
    if (!group.has(id)) group.set(id, Math.min(index, GLOBE.rings))
  }))
  const bands = []
  const points = []
  let top = 1
  GLOBE_BANDS.forEach((name, order) => {
    const rows = pages.filter(page => (GLOBE_BANDS.includes(page.band) ? page.band : 'other') === name)
    if (!rows.length) return
    const bottom = top - 2 * rows.length / pages.length
    const hi = top - (bands.length ? GLOBE.gap / 2 : 0)
    const lo = bottom + (bottom > -0.999 ? GLOBE.gap / 2 : 0)
    const band = { name, n: rows.length, mid: (top + bottom) / 2, bottom, warn: 0 }
    bands.push(band)
    rows.forEach((page, i) => {
      const y = hi - (i + 0.5) / rows.length * (hi - lo)
      const r = Math.sqrt(Math.max(0, 1 - y * y))
      const turn = (i + order * 7) * GLOBE.gold
      const g = group.has(page.id) ? group.get(page.id) : -1
      if (g >= 0) band.warn += 1
      points.push({ x: Math.cos(turn) * r, y, z: Math.sin(turn) * r, band, title: String(page.title || page.id),
        age: Number(page.age) || 0, recent: Number(page.age) < GLOBE.recent, g, s: null })
    })
    top = bottom
  })
  const marked = points.filter(point => point.g >= 0).length
  const rings = Math.min(missing.length, GLOBE.rings) + (total > GLOBE.rings ? 1 : 0)
  return { points, bands, missing, total, rings, holders: Number(map.holders) || marked, links: marked <= GLOBE.lines,
    recent: points.filter(point => point.recent).length, truncated: Boolean(map.truncated) }
}

function globeGeo(W, H, links) {
  const room = links ? 160 : 220
  const R = Math.max(0, Math.min((W - room) / 2.1, H * 0.35))
  return { R, gx: Math.max(R * 1.02 + 6, (W - R * 2.12 - 110) / 2 + R), gy: H * 0.56 }
}

function globeRing(g, R, gx, gy) {
  const a = GLOBE.angles[g] || 0
  return { x: gx + Math.sin(a) * R * 1.32, y: gy - Math.cos(a) * R * 1.32 }
}

function globeProject(p, rot, R, gx, gy) {
  const c = Math.cos(rot)
  const s = Math.sin(rot)
  const x = p.x * c + p.z * s
  const z = -p.x * s + p.z * c
  const y2 = p.y * Math.cos(GLOBE.tilt) - z * Math.sin(GLOBE.tilt)
  const z2 = p.y * Math.sin(GLOBE.tilt) + z * Math.cos(GLOBE.tilt)
  const f = 2.8 / (2.8 - z2)
  return { sx: gx + x * R * f, sy: gy - y2 * R * f, z: z2, f }
}

function globeColors(el) {
  const probe = document.createElement('span')
  el.appendChild(probe)
  const read = token => {
    probe.style.color = `var(${token})`
    return getComputedStyle(probe).color
  }
  const col = { ink: read('--ui-text-primary'), warn: read('--ui-orange'), edge: read('--ui-stroke-secondary'),
    ground: read('--wa-card') }
  probe.remove()
  const rgb = (col.ink.match(/[\d.]+/g) || []).slice(0, 3).map(Number)
  col.lift = rgb.length === 3 && rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114 < 128 ? 1.7 : 1
  return col
}

function globeDraw(ctx, model, view, group) {
  const { W, H, col, rot, hover } = view
  const { R, gx, gy } = globeGeo(W, H, model.links)
  ctx.clearRect(0, 0, W, H)
  if (R < 20) return
  const dot = (x, y, r) => { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2) }
  ctx.strokeStyle = col.ink
  ctx.globalAlpha = 0.16 * col.lift
  ctx.lineWidth = 1
  dot(gx, gy, R)
  ctx.stroke()
  ctx.strokeStyle = col.edge
  ctx.globalAlpha = 0.7
  ctx.setLineDash([2, 4])
  for (const band of model.bands.slice(0, -1)) {
    const y = band.bottom
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    ctx.beginPath()
    for (let k = 0; k <= 48; k += 1) {
      const a = Math.PI * k / 48
      const q = globeProject({ x: Math.cos(a) * r, y, z: Math.sin(a) * r }, rot, R, gx, gy)
      if (k) ctx.lineTo(q.sx, q.sy)
      else ctx.moveTo(q.sx, q.sy)
    }
    ctx.stroke()
  }
  ctx.setLineDash([])
  const shown = model.points.map(p => ({ ...globeProject(p, rot, R, gx, gy), p })).sort((a, b) => a.z - b.z)
  if (model.links) {
    ctx.strokeStyle = col.warn
    ctx.setLineDash([5, 5])
    for (const q of shown) {
      if (q.p.g < 0) continue
      const ring = globeRing(q.p.g, R, gx, gy)
      const lit = group < 0 || group === q.p.g
      ctx.globalAlpha = (q.z > -0.1 ? 0.3 + q.z * 0.5 : 0.1) * (lit ? 1 : 0.2)
      ctx.lineWidth = group === q.p.g ? 2 : 1.3
      ctx.beginPath()
      ctx.moveTo(q.sx, q.sy)
      const bend = 18 + q.p.g * 22
      ctx.quadraticCurveTo((q.sx + ring.x) / 2 + (q.sx < gx ? -bend : bend), (q.sy + ring.y) / 2 - 20, ring.x, ring.y)
      ctx.stroke()
    }
    ctx.setLineDash([])
  }
  for (const q of shown) {
    const front = (q.z + 1) / 2
    if (q.p.g >= 0) {
      const mine = group === q.p.g
      ctx.fillStyle = col.warn
      ctx.strokeStyle = col.warn
      ctx.globalAlpha = (0.35 + front * 0.65) * (group < 0 ? (model.links ? 1 : 0.6) : mine ? 1 : 0.15)
      dot(q.sx, q.sy, (model.links ? 3.6 : mine ? 3.2 : 1.8) * q.f)
      ctx.fill()
      if (model.links) { ctx.lineWidth = 1.2; dot(q.sx, q.sy, 7 * q.f); ctx.stroke() }
    } else {
      ctx.fillStyle = col.ink
      ctx.globalAlpha = Math.min(1, (q.p.recent ? 0.3 + front * 0.7 : 0.16 + front * 0.28) * col.lift)
      dot(q.sx, q.sy, (q.p.recent ? 0.9 + front * 1.5 : 0.7 + front) * q.f)
      ctx.fill()
    }
    q.p.s = q
  }
  ctx.globalAlpha = 1
  for (let g = 0; g < model.rings; g += 1) {
    const ring = globeRing(g, R, gx, gy)
    ctx.fillStyle = col.ground
    dot(ring.x, ring.y, g < GLOBE.rings ? 13 : 24)
    ctx.fill()
    ctx.strokeStyle = col.warn
    ctx.lineWidth = group === g ? 2.2 : 1.5
    ctx.setLineDash([3, 3])
    ctx.stroke()
    ctx.setLineDash([])
  }
  if (hover?.s) {
    ctx.strokeStyle = col.ink
    ctx.globalAlpha = 0.9
    ctx.lineWidth = 1.5
    dot(hover.s.sx, hover.s.sy, 6)
    ctx.stroke()
    ctx.globalAlpha = 1
  }
}

function globeMarks(t, model, W, H) {
  const { R, gx, gy } = globeGeo(W, H, model.links)
  if (R < 20) return { bands: [], rings: [] }
  let prev = -1e9
  const bands = model.bands.map(band => {
    const tall = band.warn && !model.links
    const y = Math.max(gy - band.mid * Math.cos(GLOBE.tilt) * R, prev + (tall ? 40 : 30))
    prev = y
    return { name: band.name, n: band.n, warn: tall ? band.warn : 0, x: gx + R * 1.1 + 18, y }
  })
  const rings = [...Array(model.rings).keys()].map(g => ({ g, ...globeRing(g, R, gx, gy),
    text: g < GLOBE.rings ? String(g + 1) : `+${model.total - GLOBE.rings}` }))
  return { bands, rings }
}

function WikiGlobe({ t, read }) {
  const stageRef = useRef(null)
  const canvasRef = useRef(null)
  const view = useRef({ rot: -0.35, drag: null, hover: null, W: 0, H: 0, col: null, ctx: null })
  const cache = useRef({ map: null, model: null })
  const [pinned, setPinned] = useState(-1)
  const [focus, setFocus] = useState(-1)
  const [tip, setTip] = useState(null)
  const [marks, setMarks] = useState({ bands: [], rings: [] })
  const map = read?.data?.ok === true ? read.data : null
  if (cache.current.map !== map) cache.current = { map, model: globeModel(map) }
  const model = cache.current.model
  const group = focus >= 0 ? focus : pinned
  view.current.group = group
  const paint = () => {
    const v = view.current
    if (model && v.ctx && v.col && v.W) globeDraw(v.ctx, model, v, v.group)
  }
  useLayoutEffect(() => {
    const stage = stageRef.current
    const canvas = canvasRef.current
    if (!stage || !canvas || !model) return undefined
    const layout = () => {
      const box = canvas.getBoundingClientRect()
      const v = view.current
      if (!box.width || !box.height || typeof canvas.getContext !== 'function') return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(box.width * dpr)
      canvas.height = Math.round(box.height * dpr)
      v.ctx = canvas.getContext('2d')
      if (!v.ctx) return
      v.ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      v.W = box.width
      v.H = box.height
      v.col = globeColors(stage)
      setMarks(globeMarks(t, model, v.W, v.H))
      paint()
    }
    layout()
    const watcher = typeof ResizeObserver === 'function' ? new ResizeObserver(layout) : null
    watcher?.observe(stage)
    const themed = typeof MutationObserver === 'function' ? new MutationObserver(layout) : null
    themed?.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
    return () => { watcher?.disconnect(); themed?.disconnect() }
  }, [model])
  useLayoutEffect(paint, [group, model])
  if (!map) {
    return jsx('section', { className: 'wa-globe', 'data-wa-globe': read?.error ? 'unread' : 'reading',
      'aria-label': t('wa.globeLabel'), children: jsxs('div', { className: 'wa-globe-copy', children: [
        jsx('span', { className: 'wa-globe-label', children: t('wa.globeLabel') }, 'label'),
        read?.error ? jsx(Failure, { t, text: t('wa.globeUnread'), detail: read.error }, 'failed')
          : jsx('p', { className: 'wa-globe-lead', children: t('wa.globeReading') }, 'reading')
      ] }, 'copy') }, 'globe')
  }
  const pick = event => {
    const v = view.current
    const box = canvasRef.current.getBoundingClientRect()
    const mx = event.clientX - box.left
    const my = event.clientY - box.top
    let best = null
    let gap = 324
    for (const p of model.points) {
      if (!p.s || p.s.z < -0.05) continue
      const d = (p.s.sx - mx) ** 2 + (p.s.sy - my) ** 2
      if (d < gap) { gap = d; best = p }
    }
    v.hover = best
    const named = best && best.g >= 0 ? (best.g < GLOBE.rings ? model.missing[best.g]?.name : t('wa.globeMoreBy')) : ''
    setTip(best ? { x: best.s.sx, y: best.s.sy, title: best.title,
      text: [best.band.name, t('wa.globeAge', best.age), named ? t('wa.globeNames', named) : ''].filter(Boolean).join(' · ') }
      : null)
    paint()
  }
  const handlers = {
    onPointerDown: event => {
      view.current.drag = { x: event.clientX, rot: view.current.rot }
      event.currentTarget.setPointerCapture?.(event.pointerId)
      event.currentTarget.dataset.drag = '1'
      view.current.hover = null
      setTip(null)
    },
    onPointerUp: event => { view.current.drag = null; delete event.currentTarget.dataset.drag },
    onPointerMove: event => {
      const v = view.current
      if (v.drag) { v.rot = v.drag.rot + (event.clientX - v.drag.x) * GLOBE.turn; paint(); return }
      pick(event)
    },
    onPointerLeave: () => { if (!view.current.drag) { view.current.hover = null; setTip(null); paint() } }
  }
  const top = model.missing.slice(0, GLOBE.rings)
  const rest = model.total - top.length
  const bandsText = model.bands.map(band => `${band.n} ${band.name}`).join(', ')
  const row = (g, n, name, by) => jsx('li', { children: jsxs('button', {
    type: 'button', className: 'wa-globe-miss', 'aria-pressed': pinned === g,
    onClick: () => setPinned(prev => (prev === g ? -1 : g)), onMouseEnter: () => setFocus(g),
    onMouseLeave: () => setFocus(-1), onFocus: () => setFocus(g), onBlur: () => setFocus(-1),
    children: [
      jsx('span', { className: 'wa-globe-n', 'aria-hidden': true, children: n }, 'n'),
      jsx('span', { className: 'wa-globe-name', children: name }, 'name'),
      jsx('span', { className: 'wa-globe-by', children: by }, 'by')
    ] }, 'button') }, `miss-${g}`)
  return jsxs('section', { className: 'wa-globe', 'data-wa-globe': 'ready', 'aria-label': t('wa.globeLabel'), children: [
    jsxs('div', { className: 'wa-globe-copy', children: [
      jsx('span', { className: 'wa-globe-label', children: t('wa.globeLabel') }, 'label'),
      jsx('h2', { className: 'wa-globe-head', children: model.total ? t('wa.globeMissingHead', model.total)
        : t('wa.globeAllFound') }, 'head'),
      jsx('p', { className: 'wa-globe-lead', children: [t('wa.globeLead', model.points.length, model.recent),
        model.total ? t('wa.globeHolders', model.holders) : ''].filter(Boolean).join('. ') }, 'lead'),
      top.length ? jsxs('ol', { className: 'wa-globe-list', children: [
        ...top.map((miss, g) => row(g, String(g + 1), miss.name, t('wa.globeNamedBy', miss.count))),
        rest > 0 ? row(GLOBE.rings, '+', t('wa.globeMore', rest), t('wa.globeMoreBy')) : null
      ] }, 'list') : null,
      model.truncated ? jsx('p', { className: 'wa-globe-hint', children: t('wa.globeTruncated', model.points.length) },
        'cut') : null,
      jsxs('div', { className: 'wa-globe-key', 'aria-hidden': true, children: [
        jsxs('span', { children: [jsx('i', { 'data-k': 'recent' }, 'i'), t('wa.globeKeyRecent', model.recent)] }, 'recent'),
        jsxs('span', { children: [jsx('i', { 'data-k': 'older' }, 'i'),
          t('wa.globeKeyOlder', model.points.length - model.recent)] }, 'older'),
        model.total ? jsxs('span', { children: [jsx('i', { 'data-k': 'names' }, 'i'),
          t('wa.globeKeyNames', model.holders)] }, 'names') : null,
        model.total ? jsxs('span', { children: [jsx('i', { 'data-k': 'missing' }, 'i'),
          t('wa.globeKeyMissing', model.total)] }, 'missing') : null
      ] }, 'key'),
      jsx('p', { className: 'wa-globe-hint', children: t('wa.globeDrag') }, 'hint')
    ] }, 'copy'),
    jsxs('div', { className: 'wa-globe-stage', ref: stageRef, children: [
      jsx('canvas', { className: 'wa-globe-canvas', ref: canvasRef, role: 'img',
        'aria-label': t('wa.globeAria', model.points.length, bandsText, model.recent, model.holders, model.total),
        ...handlers }, 'canvas'),
      ...marks.bands.map(band => jsxs('span', { className: 'wa-globe-band', 'aria-hidden': true,
        style: { left: `${band.x}px`, top: `${band.y}px` }, children: [
          jsxs('span', { children: [jsx('b', { children: band.name }, 'name'), String(band.n)] }, 'count'),
          band.warn ? jsx('span', { 'data-warn': '1', children: t('wa.globeBandWarn', band.warn) }, 'warn') : null
        ] }, `band-${band.name}`)),
      ...marks.rings.map(ring => jsx('span', { className: 'wa-globe-ring', 'aria-hidden': true,
        style: { left: `${ring.x}px`, top: `${ring.y}px` }, children: ring.text }, `ring-${ring.g}`)),
      tip ? jsxs('div', { className: 'wa-globe-tip', 'aria-hidden': true, style: { left: `${tip.x}px`, top: `${tip.y}px` },
        children: [jsx('b', { children: tip.title }, 'title'), jsx('span', { children: tip.text }, 'text')] }, 'tip') : null
    ] }, 'stage')
  ] }, 'globe')
}

function MetroDetail({ t, id, glyph, heading, onClose, children, candidateRef, folded }) {
  const ref = useRef(null)
  const notch = useNotch(ref, id, folded)
  return jsxs('section', { ref, className: folded ? 'wa-metro-kept' : 'wa-metro-detail', 'data-for': id,
    'data-notch': notch === null ? undefined : '1', style: notch === null ? undefined : { '--wa-notch': `${notch}px` },
    'aria-label': heading, hidden: folded || undefined, 'data-candidate-ref': candidateRef || undefined, children: [
    jsxs('div', { className: 'wa-metro-dhead', children: [
      icon(glyph),
      jsx('h2', { children: heading }, 'heading'),
      jsx(Tip, { label: t('wa.metroClose'), children: jsx(Button, { 'aria-label': t('wa.metroClose'),
        className: 'wa-metro-close', onClick: onClose, size: 'icon-sm', variant: 'outline',
        children: icon('close') }, 'close') }, 'close-tip')
    ] }, 'head'),
    jsx('div', { className: 'wa-metro-dbody', children }, 'body')
  ] }, id)
}

function askText(t, findings) {
  return [t('wa.metroAskIntro'), '', ...findings.map((f, i) => {
    const raw = findingRaw(f)
    const head = f.title ? `${f.title}: ` : ''
    return `${i + 1}. ${head}${findingEnglish(f, t)}${raw ? `\n   ${t('wa.metroAskLine')}: ${raw}` : ''}`
  }), '', t('wa.metroAskOutro')].join('\n')
}

async function placeInNewChat(text) {
  const composer = host.composer
  if (typeof composer?.insertText !== 'function') return false
  const put = async address => {
    try {
      return await composer.insertText(address, text, { mode: 'block' }) === true
    } catch {
      return false
    }
  }
  if (typeof host.newChat !== 'function') return put(null)
  host.newChat()
  for (let tries = 0; tries < 40; tries += 1) {
    await new Promise(done => setTimeout(done, 150))
    if (await put('new')) return true
  }
  return false
}

function MorningCard({ t, row, findings }) {
  const found = row.role === 'watchdog' && findings.length > 0
  const tone = !row.live || row.state === 'paused' ? 'quiet' : found ? 'warn' : row.last_status === 'error' ? 'bad'
    : row.last_status === 'ok' ? 'ok' : 'quiet'
  const result = found ? t('wa.metroResultFound', findings.length) : row.last_status === 'ok' ? t('wa.metroResultOk')
    : row.last_status === 'error' ? t('wa.metroResultFailed') : t('wa.metroResultUnknown')
  const last = row.last_run_at ? t('wa.metroLast', whenText(t, row.last_run_at), result) : t('wa.metroNeverRan')
  const next = row.state === 'paused' ? t('wa.metroPausedNote')
    : row.next_run_at ? t('wa.metroNextAt', hourOf(row.next_run_at) || whenText(t, row.next_run_at)) : ''
  return jsxs('div', { className: 'wa-metro-job', 'data-role': row.role, children: [
    jsxs('div', { className: 'wa-metro-job-head', children: [
      jsx(Dot, { t, tone, className: 'wa-metro-dot' }, 'dot'),
      jsx('span', { children: morningName(t, row.role) }, 'name')
    ] }, 'head'),
    jsx('p', { children: row.live ? [morningDoes(t, row.role), last, next].filter(Boolean).join(' ')
      : `${morningDoes(t, row.role)} ${t('wa.metroNoJobYet')}` }, 'text')
  ] }, row.role)
}

function WikiDetail({ t, model, reads, onClose }) {
  const [asked, setAsked] = useState('')
  const { runs, watch } = reads
  const { findings, checkedAt, since, pages, morning } = model.wiki
  const ask = async () => {
    const placed = await placeInNewChat(askText(t, findings))
    setAsked(placed ? t('wa.metroAskDone') : t('wa.metroAskNoChat'))
  }
  const heading = typeof pages === 'number' ? t('wa.metroWikiHead', t('wa.metroPages', pages))
    : t('wa.metroWikiStation')
  const lead = findings.length ? since ? t('wa.metroFoundSince', findings.length, since)
    : checkedAt ? t('wa.metroFoundAt', findings.length, whenText(t, checkedAt)) : t('wa.metroProblems', findings.length)
    : !runs.data && !runs.error ? t('wa.metroReading') : model.wiki.check || model.wiki.logged
      ? t('wa.metroNoProblemsText') : t('wa.metroNoCheckText')
  return jsxs(MetroDetail, { t, id: 'wiki', glyph: 'book', heading, onClose, children: [
    runs.error ? jsx(Failure, { t, text: t('wa.metroChecksUnread'), detail: runs.error }, 'runs-failed') : null,
    watch.error ? jsx(Failure, { t, text: t('wa.metroChecksUnread'), detail: watch.error }, 'watch-failed') : null,
    jsx(WikiGlobe, { t, read: reads.map }, 'globe'),
    jsx('strong', { className: 'wa-metro-lead', children: lead }, 'lead'),
    findings.length ? jsx('ol', { className: 'wa-metro-findings', children: findings.map((f, i) => jsxs('li', {
      className: 'wa-metro-finding', children: [
        jsx('span', { className: 'wa-metro-finding-n', children: String(i + 1) }, 'n'),
        jsxs('div', { className: 'wa-metro-finding-body', children: [
          jsx('strong', { children: f.title || findingEnglish(f, t) }, 'heading'),
          f.title ? jsx('p', { children: findingEnglish(f, t) }, 'english') : null,
          findingRaw(f) ? jsxs('details', { className: 'wa-metro-raw', children: [
            jsx('summary', { children: t('wa.metroRawLine') }, 'summary'),
            jsx(PanelBlock, { className: 'wa-mono', children: findingRaw(f) }, 'raw')
          ] }, 'raw') : null
        ] }, 'body')
      ] }, `${f.kind}-${i}`)) }, 'list') : null,
    findings.length ? jsxs('div', { className: 'wa-metro-acts', children: [
      jsx(Button, { className: 'wa-metro-ask', variant: 'outline', onClick: ask,
        children: t('wa.metroAsk') }, 'ask'),
      jsxs('span', { className: 'wa-metro-note', children: [icon('info'),
        jsx('span', { children: t('wa.metroAskHint') }, 'text')] }, 'hint')
    ] }, 'acts') : null,
    jsx('div', { className: 'wa-live', 'aria-live': 'polite', children: asked
      ? jsx('p', { className: 'wa-metro-note', 'data-asked': '1', children: asked }, 'asked') : null }, 'live'),
    jsx('h3', { className: 'wa-metro-sub', children: t('wa.metroMorning') }, 'morning-heading'),
    jsx('div', { className: 'wa-metro-jobs', children: morning.map(row => jsx(MorningCard, { t, row, findings },
      row.role)) }, 'morning')
  ] }, 'wiki')
}

function HarvestDetail({ t, model, reads, onClose }) {
  const { auto, jobs, harvest, runs } = reads
  const { known, role, latest, running, failed, cause, cost } = model.harvest
  const refused = jobs.error || refusal(t, jobs.data)
  const unknown = t('wa.metroNotReported')
  const names = model.lines.filter(line => line.row.found && line.row.enabled).map(line => line.name)
  const outcome = running ? t('wa.metroRunRunning') : failed ? t('wa.metroRunFailed') : ''
  const spent = typeof cost === 'number' ? t('wa.metroHvCost', cost.toFixed(2)) : ''
  const took = latest && !running && typeof latest.duration_ms === 'number'
    ? t('wa.metroFinishedIn', Math.max(1, Math.round(latest.duration_ms / 1000))) : ''
  const rows = [
    { label: t('wa.metroWhatItDoes'), value: names.length ? t('wa.metroHarvestDoes', listText(t, names))
      : t('wa.metroHarvestDoesAny') },
    { label: t('wa.metroTimetable'), value: !known ? unknown : role?.schedule ? capFirst(schedHuman(t, role.schedule))
      : t('wa.jobNoSchedule') },
    { label: t('wa.metroNextRun'), value: !known ? unknown : !role?.live ? '—' : role.state === 'paused' ? t('wa.runPaused')
      : role.next_run_at ? [capFirst(whenText(t, role.next_run_at)), untilText(t, role.next_run_at)]
        .filter(Boolean).join(' · ') : '—' },
    { label: t('wa.metroLastRun'), value: !known ? unknown : role?.last_run_at
      ? [capFirst(whenText(t, role.last_run_at)), took, outcome, spent].filter(Boolean).join(' · ') : t('wa.runNever') }
  ]
  return jsxs(MetroDetail, { t, id: 'harvest', glyph: 'sparkle', heading: t('wa.metroHarvestHead'), onClose,
    children: [
      harvest.error ? jsx(Failure, { t, text: t('wa.metroLinesUnread'), detail: harvest.error }, 'lines-failed') : null,
      refused ? jsx(Failure, { t, text: t('wa.loadFailed'), detail: refused }, 'jobs-failed') : null,
      runs.error ? jsx(Failure, { t, text: t('wa.loadFailed'), detail: runs.error }, 'runs-failed') : null,
      jsx(PanelMeta, { className: 'wa-kv wa-metro-kv', rows }, 'facts'),
      failed ? jsxs('div', { className: 'wa-metro-error', children: [
        jsx('p', { children: cause ? t('wa.metroHvFailReason', shortText(cause)) : t('wa.metroHvFailNoReason') },
          'short'),
        cause ? jsxs('details', { className: 'wa-metro-raw', children: [
          jsx('summary', { children: t('wa.metroShowError') }, 'summary'),
          jsx(PanelBlock, { className: 'wa-mono', children: cause }, 'raw')
        ] }, 'raw') : null
      ] }, 'error') : null,
      known ? jsx(JobsCard, { t, jobs, auto, only: HARVEST_ROLE }, 'job') : null
    ] }, 'harvest')
}

function LineDetail({ t, id, model, reads, onClose }) {
  const { harvest } = reads
  const line = model.lines.find(row => `line:${row.id}` === id)
  const cursor = line?.row?.cursor
  const dated = Boolean(isoParts(cursor))
  const cursorText = dated ? capFirst(whenText(t, cursor)) : String(cursor || t('wa.metroNotReported'))
  const rows = line ? [
    { label: t('wa.metroBrings'), value: t('wa.metroBringsText', line.name) },
    { label: t('wa.metroCursor'), value: cursorText },
    { label: t('wa.metroLineFolder', line.name), value: line.row.found ? t('wa.metroFound') : t('wa.metroNotFound') },
    { label: t('wa.metroLineState'), value: !line.row.enabled ? t('wa.metroLineOffState')
      : line.state === 'unread' ? t('wa.metroLineOnUnread') : line.row.found ? t('wa.metroLineOnState')
        : model.harvest.stopsAll ? t('wa.metroLineOnMissing') : t('wa.metroLineOnSkipped') }
  ] : []
  const honest = [t('wa.metroHonest'), dated ? t('wa.metroHonestFrom', whenText(t, cursor)) : ''].filter(Boolean)
  return jsxs(MetroDetail, { t, id, glyph: 'comment-discussion',
    heading: line ? t('wa.metroLineHead', line.name) : t('wa.metroLine'), onClose, children: [
      harvest.error && !line ? jsx(Failure, { t, text: t('wa.metroLinesUnread'), detail: harvest.error }, 'failed')
        : null,
      line ? jsx(PanelMeta, { className: 'wa-kv wa-metro-kv', rows }, 'facts')
        : jsx('p', { className: 'wa-metro-lead', children: t('wa.metroNotReported') }, 'gone'),
      line?.row?.found ? jsxs('p', { className: 'wa-metro-note', children: [icon('info'),
        jsx('span', { children: honest.join(' ') }, 'text')] }, 'honest') : null
    ] }, id)
}

function ReviewDetail({ t, model, reads, onClose }) {
  const { folio, cands } = reads
  const [shown, setShown] = useState(null)
  const inventory = { ...folio.recovery, busy: folio.busy, refresh: folio.refresh }
  const list = reads.cands?.data?.candidates || []
  const at = shown ? list.findIndex(row => row.ref === shown) : -1
  const heading = at >= 0 ? t('wa.metroReviewAt', at + 1, list.length)
    : model.review.count ? t('wa.metroReviewHead', t('wa.metroDrafts', model.review.count)) : t('wa.metroReview')
  return jsxs(MetroDetail, { t, id: 'review', glyph: 'inbox', heading, onClose, candidateRef: shown, children: [
    folio.error ? jsx(Failure, { t, text: t('wa.candReadFailed'), detail: folio.error }, 'context-error') : null,
    folio.scope ? jsx(OwnerSetup, { t, setup: folio.setup, scope: folio.scope,
      onComplete: cands.refresh, onReload: folio.refresh }, `setup-${folio.scope.key}`) : null,
    folio.scope ? jsx(RecoveryList, { t, inventory, scope: folio.scope,
      onComplete: cands.refresh }, `recovery-${folio.scope.key}`) : null,
    folio.scope ? jsx(CandidatesCard, { t, cands, scope: folio.scope, onShown: setShown,
      engineUpdate: Boolean(model.update) }, `candidates-${folio.scope.key}`)
      : folio.error ? null : jsx(Loading, {}, 'context-loading')
  ] }, 'review')
}

const RUN_KIND = {
  [HARVEST_ROLE]: { glyph: 'sparkle', name: t => t('wa.metroHarvest'), did: t => t('wa.metroDidHarvest') },
  watchdog: { glyph: 'eye', name: t => t('wa.metroDailyCheck'), did: t => t('wa.metroDidCheck') },
  ingest_watch: { glyph: 'inbox', name: t => t('wa.metroNewSources'), did: t => t('wa.metroDidSources') },
  autocommit: { glyph: 'git-commit', name: t => t('wa.metroSaving'), did: t => t('wa.metroDidSave') }
}
const HISTORY_SPAN = { '24h': t => t('wa.metroSpan24h'), '7d': t => t('wa.metroSpan7d'), all: t => t('wa.metroSpanAll') }
const HISTORY_NEXT = { '24h': '7d', '7d': 'all' }
const HISTORY_ROWS = 100
const LATE_S = 600

function runOutcome(t, run, role) {
  if (ACTIVE_STATUS.includes(run.status)) return { tone: 'ask', text: t('wa.metroRunRunningNow') }
  const found = Number(run.findings_count) || 0
  if (role === 'watchdog' && found > 0) return { tone: 'warn', text: t('wa.metroRunFound', found) }
  if (run.status !== 'completed') {
    const body = ['error', 'output'].includes(run.body_source) ? String(run.body || '').trim() : ''
    return { tone: 'bad', text: run.status === 'failed' ? t('wa.metroRunFailedNow')
      : String(run.status_label || run.status || '').toLowerCase() || t('wa.metroRunFailedNow'),
    why: body ? shortText(body) : '', raw: body }
  }
  return { tone: 'ok', text: typeof run.duration_ms === 'number' && run.duration_ms >= 1000
    ? t('wa.metroRunFinishedIn', Math.round(run.duration_ms / 1000)) : t('wa.metroRunFinished') }
}

function lateNote(t, rows) {
  const late = rows.filter(row => Number(row.run.lateness_s) >= LATE_S && row.run.scheduled_at)
  if (!late.length) return ''
  const newest = late[0]
  const morning = late.filter(row => MORNING_ROLES.includes(row.role)
    && row.run.scheduled_at === newest.run.scheduled_at)
  if (MORNING_ROLES.includes(newest.role) && morning.length > 1) {
    return t('wa.metroLateMorning', hourOf(newest.run.scheduled_at) || '—', hourOf(newest.run.at) || '—')
  }
  return t('wa.metroLateOne', newest.name, hourOf(newest.run.scheduled_at) || '—', hourOf(newest.run.at) || '—')
}

function TechnicalLog() {
  const winRef = useRef(WINDOW_FOR_PRESET.all)
  const history = useHealthPolling(() => healthApi.jobs(winRef.current), 60000)
  return jsx(JobRunsPage, { data: history.data, error: history.error, refresh: history.refresh, busy: history.busy,
    winRef }, 'runs')
}

function HistoryDetail({ t, model, reads, onClose }) {
  const [win, setWin] = useState('24h')
  const [full, setFull] = useState(false)
  const own = usePolling(() => (win === '24h' ? Promise.resolve(null) : healthApi.jobs(win)),
    win === '24h' ? 0 : 60000, [win])
  const source = win === '24h' ? reads.runs : own
  const data = source.data && source.data.window === win ? source.data : null
  const roleOf = new Map(model.harvest.roles.filter(row => row.id).map(row => [String(row.id), row.role]))
  const rows = (data?.runs || []).slice().sort((a, b) => stampAt(b) - stampAt(a)).map(run => {
    const role = roleOf.get(String(run.job_id)) || ''
    const kind = RUN_KIND[role]
    return { run, role, glyph: kind?.glyph || 'watch', name: kind ? kind.name(t) : String(run.job_name || run.job_id || '—'),
      did: kind ? kind.did(t) : '', outcome: runOutcome(t, run, role) }
  })
  const span = HISTORY_SPAN[win](t)
  const heading = data ? t('wa.metroHistoryHead', span, rows.length) : t('wa.metroHistory')
  const late = lateNote(t, rows)
  const next = HISTORY_NEXT[win]
  return jsxs(MetroDetail, { t, id: 'history', glyph: 'history', heading, onClose, children: [
    source.error ? jsx(Failure, { t, text: t('wa.metroHistoryRead'), detail: source.error }, 'failed') : null,
    !data && !source.error ? jsx(Loading, {}, 'loading') : null,
    data && !rows.length ? jsx('p', { className: 'wa-metro-lead', children: t('wa.metroHistoryEmpty', span) }, 'empty')
      : null,
    rows.length ? jsx('ol', { className: 'wa-metro-runs', children: rows.slice(0, HISTORY_ROWS).map(row => jsxs('li', {
      className: 'wa-metro-run', 'data-role': row.role || undefined, 'data-outcome': row.outcome.tone, children: [
        jsx('span', { className: 'wa-metro-run-at', children: capFirst(whenText(t, row.run.at)) }, 'at'),
        jsx('span', { className: 'wa-metro-run-glyph', children: icon(row.glyph) }, 'glyph'),
        jsxs('span', { className: 'wa-metro-run-what', children: [
          jsx('strong', { children: row.name }, 'name'),
          row.did ? jsx('span', { children: row.did }, 'did') : null,
          row.outcome.why ? jsx('span', { 'data-reason': '1', children: row.outcome.why }, 'reason') : null,
          row.outcome.raw ? jsxs('details', { className: 'wa-metro-raw', children: [
            jsx('summary', { children: t('wa.metroShowError') }, 'summary'),
            jsx(PanelBlock, { className: 'wa-mono', children: row.outcome.raw }, 'raw')
          ] }, 'raw') : null
        ] }, 'what'),
        jsxs('span', { className: 'wa-metro-run-out', children: [
          jsx(Dot, { t, tone: row.outcome.tone, className: 'wa-metro-dot' }, 'dot'),
          jsx('span', { children: row.outcome.text }, 'text')
        ] }, 'out')
      ] }, String(row.run.id ?? `${row.run.job_id}-${row.run.at}`))) }, 'runs') : null,
    rows.length > HISTORY_ROWS ? jsx('p', { className: 'wa-metro-note', children: t('wa.metroHistoryCap', HISTORY_ROWS) },
      'cap') : null,
    late ? jsxs('p', { className: 'wa-metro-note', 'data-late': '1', children: [icon('info'),
      jsx('span', { children: late }, 'text')] }, 'late') : null,
    jsxs('div', { className: 'wa-metro-acts', children: [
      next ? jsx(Button, { className: 'wa-metro-older', variant: 'outline', onClick: () => setWin(next),
        children: win === '24h' ? t('wa.metroHistoryOlder') : t('wa.metroHistoryAll') }, 'older') : null,
      jsx(Button, { className: 'wa-metro-full', variant: 'outline', 'aria-expanded': full,
        onClick: () => setFull(open => !open), children: full ? t('wa.metroHistoryFullHide') : t('wa.metroHistoryFull') },
      'full')
    ] }, 'acts'),
    full ? jsx('div', { className: 'wa-metro-techlog', children: jsx(TechnicalLog, {}, 'log') }, 'log') : null
  ] }, 'history')
}

function SetRow({ label, note, value, actions, inline }) {
  return jsxs('div', { className: 'wa-set-row', children: [
    jsxs('div', { className: 'wa-set-label', children: [
      jsx('div', { className: 'wa-set-name', children: label }, 'name'),
      note ? jsx('div', { className: 'wa-set-note', children: note }, 'note') : null
    ] }, 'label'),
    jsx('div', { className: 'wa-set-value', children: value }, 'value'),
    actions ? jsx('div', { className: inline ? 'wa-set-acts wa-inline' : 'wa-set-acts', children: actions }, 'acts') : null
  ] })
}

function SettingsDetail({ t, reads, model, jumpTo, onJumped, onClose, folded }) {
  const { auto, jobs, engine } = reads
  const [reveal, setReveal] = useState(null)
  const info = auto.data || null
  const settings = info?.settings || null
  const scripts = info?.scripts || {}
  const total = Object.keys(scripts).length
  const inPlace = Object.values(scripts).filter(Boolean).length
  const missing = Object.keys(scripts).filter(name => !scripts[name])
  const roles = jobs.data && jobs.data.ok !== false ? jobs.data.roles || [] : []
  const needs = {
    root: Boolean(info) && settings?.project?.ok !== true,
    jobs: Boolean(jobs.error) || jobs.data?.ok === false
      || roles.some(row => !row.live || row.state === 'paused' || !row.target?.ok),
    install: Boolean(model?.engineAsk) || missing.length > 0
  }
  useEffect(() => {
    if (!reveal) return
    const target = document.getElementById(`wa-sec-${reveal.id}`)
    target?.scrollIntoView?.({ behavior: prefersReduced() ? 'auto' : 'smooth', block: 'start' })
    target?.focus?.({ preventScroll: true })
  }, [reveal])
  useEffect(() => {
    if (!jumpTo) return
    setReveal({ id: jumpTo })
    onJumped?.()
  }, [jumpTo])
  const count = roles.length ? t('wa.jobsLive', roles.filter(r => r.live && r.state !== 'paused').length,
    roles.filter(r => r.live && r.state === 'paused').length, roles.length) : ''
  const chip = (tone, text) => jsx('span', { className: 'wa-set-chip', 'data-chip': tone, children: text }, 'chip')
  const chips = {
    root: info ? (settings?.project?.ok === true ? chip('ok', t('wa.ok')) : chip('warn', t('wa.metroWikiUnchecked'))) : null,
    jobs: count ? jsx('span', { className: 'wa-jobs-count', children: count }, 'meta') : null,
    install: info ? (missing.length ? chip('bad', t('wa.metroFilesMissing', missing.join(', ')))
      : (model?.engineAsk ? chip('ask', t('wa.setNeedsYou')) : chip('ok', t('wa.metroFilesInPlace', inPlace, total))))
      : null
  }
  const section = (id, glyph, heading, body) => jsxs('div', { className: 'wa-card g-panel wa-metro-sec',
    'data-sec': id, 'data-need': needs[id] ? 'true' : undefined, children: [
      jsxs('div', { className: 'g-panel-head', children: [
        icon(glyph),
        jsx('h2', { className: 'g-panel-title', id: `wa-h-${id}`, children: heading }, 'heading'),
        chips[id]
      ] }, 'summary'),
    jsx('section', { 'aria-labelledby': `wa-h-${id}`, className: 'wa-metro-secbody', id: `wa-sec-${id}`,
      tabIndex: -1, children: body }, 'body')
  ] }, id)
  return jsxs(MetroDetail, { t, id: 'settings', glyph: 'gear', heading: t('wa.metroSettings'), onClose, folded,
    children: [
    auto.error && !info ? jsx(Failure, { t, text: t('wa.loadFailed'), detail: auto.error }, 'failed') : null,
    !info && !auto.error ? jsx(Loading, {}, 'loading') : null,
    section('root', 'folder', t('wa.rootSection'), jsx(RootCard, { t, auto, refreshAuto: auto.refresh }, 'card')),
    section('jobs', 'calendar', t('wa.jobsSection'),
      jsx(JobsCard, { t, jobs, auto, onInstall: () => setReveal({ id: 'install' }) }, 'card')),
    section('install', 'tools', t('wa.install'),
      jsx(InstallCard, { t, auto, onEngineState: () => engine.refresh() }, 'card'))
  ] }, 'settings')
}

function MetroDetailFor({ t, id, model, reads, onClose }) {
  if (id === 'wiki') return jsx(WikiDetail, { t, model, reads, onClose }, id)
  if (id === 'harvest') return jsx(HarvestDetail, { t, model, reads, onClose }, id)
  if (id === 'review') return jsx(ReviewDetail, { t, model, reads, onClose }, id)
  if (id === 'history') return jsx(HistoryDetail, { t, model, reads, onClose }, id)
  return jsx(LineDetail, { t, id, model, reads, onClose }, id)
}

function Page() {
  const t = usePluginI18n(PLUGIN_ID)
  const [open, setOpen] = useState(null)
  const [jumpTo, setJumpTo] = useState(null)
  const kept = useRef(false)
  const checked = useRef(false)
  if (open === 'settings') kept.current = true
  if (open === 'wiki') checked.current = true
  const reads = useMetroReads(checked.current)
  const close = () => { setJumpTo(null); setOpen(null) }
  const toggle = id => { setJumpTo(null); setOpen(previous => (previous === id ? null : id)) }
  const model = metroModel(t, reads)
  const gone = Boolean(open?.startsWith('line:')) && !model.loading
    && !model.lines.some(line => `line:${line.id}` === open)
  useEffect(() => { if (gone) setOpen(null) }, [gone])
  const act = action => {
    if (action.retry) { reads.refresh(); return }
    setJumpTo(action.jump || null)
    setOpen(action.open)
  }
  const nav = (id, glyph, label) => jsxs('button', {
    type: 'button', className: 'wa-metro-navbtn', 'data-wa-nav': id, 'aria-pressed': open === id,
    'aria-label': label, onClick: () => toggle(id),
    children: [icon(glyph), jsx('span', { className: 'wa-metro-navlabel', children: label }, 'label')]
  }, id)
  return jsxs('div', { className: 'wa-shell', children: [
    jsx('style', { children: SHELL_STYLE }, 'shell-style'),
    jsxs('div', { className: 'wa-root wa-metro', children: [
      jsx('style', { children: STYLE }, 'style'),
      jsxs('header', { className: 'wa-metro-head', children: [
        icon('book'),
        jsx('h1', { children: t('wa.title') }, 'heading'),
        jsxs('div', { className: 'wa-metro-nav', children: [
          open === 'history' ? null : jsx(Tip, { label: t('wa.refresh'), children: jsx(Button, {
            'aria-label': t('wa.refresh'), className: 'wa-metro-refresh', loading: reads.busy, onClick: reads.refresh,
            size: 'icon-sm', variant: 'outline', children: icon('refresh') }, 'refresh') }, 'refresh-tip'),
          nav('history', 'history', t('wa.metroHistory')),
          nav('settings', 'gear', t('wa.metroSettings'))
        ] }, 'nav')
      ] }, 'head'),
      model.loading ? jsx(MetroSkeleton, { t }, 'skeleton')
        : jsx(MetroMap, { t, model, reads, open, toggle }, 'map'),
      !model.loading && model.alert && !(open && model.alert.action?.open === open && !model.alert.action?.jump)
        ? jsx(MetroBar, { t, alert: model.alert, onAct: act }, 'bar') : null,
      !model.loading && model.engineAsk && model.alert?.key !== 'engine' ? jsx(EngineNotice, { t,
        state: model.engineAsk, onAct: () => act({ open: 'settings', jump: 'install' }) }, 'engine') : null,
      !model.loading && !open ? jsx(WikiGlobe, { t, read: reads.map }, 'globe') : null,
      open && open !== 'settings' ? jsx(MetroDetailFor, { t, id: open, model, reads, onClose: close },
        `detail-${open}`) : null,
      open === 'settings' || kept.current ? jsx(SettingsDetail, { t, reads, model, jumpTo, onJumped: () => setJumpTo(null),
        onClose: close, folded: open !== 'settings' }, 'settings') : null
    ] }, 'metro')
  ] })
}

const SHELL_STYLE = `
.wa-shell{height:100%;min-height:0;display:flex;flex-direction:column;gap:0;
  container-type:inline-size;background:var(--ui-chat-surface-background);color:var(--ui-text-primary)}
.wa-shell input{caret-color:var(--ui-text-primary)}
.wa-shell [data-slot="button"][data-variant="outline"]:not([data-size^="icon"]){border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-lg,2.4px);box-shadow:none}
.wa-shell [data-slot="badge"]{font-size:12px}.wa-shell [data-slot="panel-block"]{font-size:12px}
.wa-shell :is(dt,dd){font-size:max(12px,1em)}
.wa-shell dt{color:var(--ui-text-secondary)}
.wa-shell [data-slot="segmented-control"] button{font-size:12px}
.wa-shell .wa-body-wrap,.wa-shell .wa-root,.wa-shell .fl-index-scroll,.wa-shell .fl-proposal,.wa-shell .fl-reason,.wa-shell .fl-facts,.wa-shell .wa-scroll{
  scrollbar-width:thin;scrollbar-color:var(--ui-text-tertiary) transparent}
.wa-shell .fl-index-scroll::-webkit-scrollbar,.wa-shell .fl-proposal::-webkit-scrollbar,.wa-shell .fl-reason::-webkit-scrollbar,.wa-shell .fl-facts::-webkit-scrollbar{width:6px;height:6px}
.wa-shell .fl-index-scroll::-webkit-scrollbar-thumb,.wa-shell .fl-proposal::-webkit-scrollbar-thumb,.wa-shell .fl-reason::-webkit-scrollbar-thumb,.wa-shell .fl-facts::-webkit-scrollbar-thumb{background:var(--ui-text-tertiary);border-radius:var(--radius-lg,2.4px)}
.wa-shell .fl-index-scroll::-webkit-scrollbar-track,.wa-shell .fl-proposal::-webkit-scrollbar-track,.wa-shell .fl-reason::-webkit-scrollbar-track,.wa-shell .fl-facts::-webkit-scrollbar-track{background:transparent}
.wa-shell ::selection{background:color-mix(in srgb,var(--ui-accent) 28%,transparent);color:var(--ui-text-primary)}
.wa-shell [aria-live]:empty{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.wa-shell :is(.fl-layout,.pa-chronicle>.pa-sec,.pa-health>.pa-sec,.pa-health>.pa-kpis){
  border:1px solid var(--hx-line);border-radius:var(--radius-xl,3.2px);background:var(--hx-panel);
  box-shadow:inset 0 1px 0 color-mix(in srgb,var(--ui-text-primary) 6%,transparent)}
.wa-shell :is(.fl-index,.fl-decision,.ch-journal .pa-drawer){background:var(--hx-raised)}
.wa-shell :is(.pa-chronicle .pa-sectitle,.pa-health>.pa-sec>.pa-sectitle){background:transparent}
.wa-shell :is(.fl-index,.fl-index-note,.fl-document-top,.fl-views,.fl-checks,.fl-decision,.fl-facts dt,
  .ch-journal .pa-drawer,.ch-summary,.ch-error-section,.ch-duration-section,
  .ch-trace-note,.ch-technical,.pa-chronicle>.pa-sec>.pa-sectitle,.pa-health>.pa-sec>.pa-sectitle,
  .pa-health .pa-kpi,.pa-health .pa-kpi[data-state]){border-color:var(--hx-line)}
.wa-shell :is(.ch-inspector .pa-drawer-head,
  .ch-journal .ch-inspector-body,.fl-change,.fl-decision){--wa-pad:18px;padding-left:var(--wa-pad);padding-right:var(--wa-pad)}
.wa-shell :is(.ch-summary,.ch-error-section,.ch-duration-section,.ch-trace-note,.ch-technical,
  .fl-document-top,.fl-views,.fl-checks){margin-left:calc(var(--wa-pad) * -1);margin-right:calc(var(--wa-pad) * -1);
  padding-left:var(--wa-pad);padding-right:var(--wa-pad)}
.wa-shell :is(.fl-facts){margin-left:calc(var(--wa-pad) * -1);margin-right:calc(var(--wa-pad) * -1)}
.wa-shell :is(.fl-facts dt,.fl-facts dd){padding-left:var(--wa-pad);padding-right:var(--wa-pad)}
.wa-shell .fl-index-note{margin:0 -8px;padding:10px 16px 0}
.wa-shell .ch-journal .ch-inspector-body>div{padding-left:0;padding-right:0}
.wa-shell .ch-technical .pa-findlist{width:auto;margin-left:calc(var(--wa-pad) * -1);margin-right:calc(var(--wa-pad) * -1)}
.wa-shell .ch-technical .pa-findlist [data-panel-row]{border-radius:0;padding-left:calc(var(--wa-pad) + 2px);padding-right:calc(var(--wa-pad) + 2px)}
.wa-shell .pa-health>.pa-sec>.pa-sectitle{padding:13px 18px;border-bottom:1px solid var(--hx-line)}
.wa-shell .pa-health>.pa-sec>:not(.pa-sectitle,.pa-fr){padding:14px 18px 16px}
.wa-shell .pa-health>.pa-legend{border-top:0;padding:14px 0 0}
@container (max-width:850px){.wa-shell .fl-facts{margin-left:0;margin-right:0}
  .wa-shell .fl-facts :is(dt,dd){padding-left:0;padding-right:0}}
`

const ACT_LANES = 24
const TYPE = { micro: 12, caption: 12, body: 12, lead: 13, ring: 16, figure: 24,
  heading: 24 }
const H = { freshness: 122, kpi: 86, chart: 60, activity: 72, logHead: 24,
  logRow: 52, logRowNarrow: 64, findRow: 28, logScroll: 520, drawer: 420 }
const DAYS = 12
const MAX_DAYS = 31
const LABEL_W = 160
const GRID = '3px 62px minmax(0,1.15fr) minmax(0,1fr) minmax(0,1.05fr) 12px'
const TONE = {
  bad: { variant: 'destructive', color: 'var(--ui-red)' },
  warn: { variant: 'warn', color: 'var(--ui-orange)' },
  neutral: { variant: 'muted', color: 'var(--ui-text-quaternary)' }
}
const toneOf = tone => TONE[tone] || TONE.neutral
const toneKey = tone => (TONE[tone] ? tone : 'neutral')

const TIP = { set: null }

function hoverTip(text) {
  const send = e => {
    const rect = e.currentTarget?.getBoundingClientRect?.()
    TIP.set?.({
      text,
      x: Math.round(rect ? rect.left : 0),
      y: Math.round(rect ? rect.bottom : 0),
      h: Math.round(rect ? rect.height : 0)
    })
  }
  return {
    onMouseEnter: send,
    onFocus: send,
    onMouseLeave: () => TIP.set?.(null),
    onBlur: () => TIP.set?.(null)
  }
}


const WD_STYLE = `
:root:not(.dark) .pa-root .pa-badge[data-tone]{color:var(--ui-text-primary)}
.pa-icon[data-busy="1"] svg{animation:pa-spin ${MOTION.spin.ms}ms ${MOTION.spin.ease} infinite}
@keyframes pa-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.pa-icon[data-busy="1"] svg{animation:none}}
.pa-kpi,.pa-chart{border:1px solid var(--hx-line);border-radius:var(--radius-xl,3.2px);
  background:var(--hx-card);overflow:hidden}
.pa-kpi{display:flex;flex-direction:column;gap:3px;padding:10px 12px}
.pa-kpi-fig{display:inline-block}
.pa-kpi[data-state="bad"]{border-color:color-mix(in srgb,var(--ui-red) 50%,transparent);
  background:color-mix(in srgb,var(--ui-red) 6%,var(--hx-card))}
.pa-kpi[data-state="warn"]{border-color:color-mix(in srgb,var(--ui-orange) 42%,transparent)}
.pa-kpi-lab{font-size:${TYPE.caption}px;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ui-text-secondary);line-height:1.25}
.pa-chart{margin:6px 12px 0;padding:6px 8px}
.pa-ck{display:inline-flex;align-items:center;gap:10px}
.pa-ck-item{display:inline-flex;align-items:center;gap:4px;font-size:${TYPE.caption}px;
  color:var(--ui-text-tertiary)}
.pa-ck-dot{background:var(--ui-text-quaternary)}
.pa-ck-dot[data-tone="bad"]{background:var(--ui-red)}
.pa-ck-dot[data-tone="warn"]{background:var(--ui-orange)}
.pa-legend{padding:10px 12px 14px;display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.pa-tl-legend{display:flex;flex-wrap:wrap;gap:12px;margin:6px 12px 0;font-size:${TYPE.caption}px;
  color:var(--ui-text-tertiary)}
.pa-tl-legend span{display:inline-flex;align-items:center;gap:5px}
.pa-fr{display:grid;grid-template-columns:112px 1fr;gap:14px;align-items:center;
  margin:6px 12px 8px;padding:2px 0;min-height:${H.freshness}px;box-sizing:border-box}
.pa-ring{position:relative;display:inline-block}
.pa-ring svg{display:block}
.pa-ring-mid{position:absolute;inset:0;display:grid;place-content:center;text-align:center;
  padding:0 8px;box-sizing:border-box}
.pa-ring-mid b{font:600 ${TYPE.ring}px/1.1 ui-monospace,monospace;display:block;
  color:var(--ui-text-primary);white-space:nowrap}
.pa-ringcol{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
.pa-fr-cap{font-size:${TYPE.micro}px;line-height:1.35;color:var(--ui-text-tertiary);
  text-align:center;display:block}
.pa-fr-body{display:flex;flex-direction:column;gap:7px;min-width:0}
.pa-fr-head{font-size:${TYPE.lead}px;font-weight:600;color:var(--ui-text-primary)}
.pa-fr-sum{font-size:${TYPE.body}px;color:var(--ui-text-secondary)}
.pa-orbs{display:flex;gap:8px;flex-wrap:wrap;max-height:96px;overflow-y:auto;
  overscroll-behavior:contain;scrollbar-width:thin;
  scrollbar-color:color-mix(in srgb, var(--ui-text-tertiary) 45%, transparent) transparent}
.pa-orb{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--radius-xl,3.2px);
  border:1px solid var(--hx-line);background:var(--ui-bg-secondary);cursor:pointer;
  font:inherit;color:inherit}
.pa-orb span{display:block;text-align:left}
.pa-orb .n{font-size:${TYPE.body}px;color:var(--ui-text-primary);max-width:120px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.pa-orb .m{font:${TYPE.micro}px/1.4 ui-monospace,monospace;color:var(--ui-text-secondary);
  max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pa-spark{display:block;width:100%;height:16px;margin-top:2px}
.pa-delta{font:${TYPE.caption}px/1 ui-monospace,monospace;margin-left:5px;
  color:var(--ui-text-secondary);display:inline-flex;align-items:center;gap:1px}
.pa-delta>i{font-style:normal}
.pa-delta[data-dir="good"]>i{color:var(--ui-green)}
.pa-delta[data-dir="bad"]>i{color:var(--ui-orange)}
:root:not(.dark) .pa-root .pa-delta[data-dir]>i{color:var(--ui-text-primary)}
.pa-act{margin:4px 12px 8px;padding:7px 8px;border:1px solid var(--hx-line);
  border-radius:var(--radius-xl,3.2px);background:var(--hx-card);display:grid;gap:4px;align-content:start}
.pa-act-axis{display:grid;grid-template-columns:${LABEL_W}px 1fr;gap:8px;
  font:${TYPE.micro}px/1.4 ui-monospace,monospace;color:var(--ui-text-secondary)}
.pa-act-axis>span:last-child{display:flex;justify-content:space-between}
.pa-act-row{display:grid;grid-template-columns:${LABEL_W}px 1fr;gap:8px;align-items:center}
.pa-act-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:${TYPE.body}px;
  color:var(--ui-text-secondary)}
.pa-act-name{display:flex;gap:8px;align-items:center;min-width:0;height:18px;line-height:18px}
.pa-act-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pa-act-count{margin-left:auto;font-weight:500;font-variant-numeric:tabular-nums;color:var(--ui-text-secondary)}
.pa-act-cells{display:grid;gap:2px}
.pa-act-cell{height:14px;border-radius:var(--radius-md,2px);
  background:linear-gradient(var(--ui-stroke-secondary),var(--ui-stroke-secondary)) center/100% 2px no-repeat}
.pa-act-cell[data-tone="delivered"]{background:var(--ui-text-quaternary)}
.pa-act-cell[data-tone="warn"]{background:var(--ui-orange)}
.pa-act-cell[data-tone="bad"]{background:var(--ui-red)}
.pa-bar-col{flex:1 1 0;min-width:0;height:100%;display:flex;flex-direction:column;align-items:center;
  justify-content:flex-end;gap:0;border-radius:var(--radius-lg,2.4px) var(--radius-lg,2.4px) 0 0;padding:0 2px}
.pa-bar-count{margin-bottom:3px;line-height:1}
.pa-bar-day{align-self:stretch;text-align:center;line-height:1;padding-top:4px;
  border-top:1px solid var(--hx-line)}
.pa-bar-col[data-zero="0"] .pa-bar-day{color:var(--ui-text-secondary);font-weight:600;
  border-top-color:var(--ui-purple)}
.pa-bar-col:hover{background:color-mix(in srgb, var(--ui-text-primary) 6%, transparent)}
.pa-bar-col:hover .pa-bar-count{color:var(--ui-text-primary)}
.pa-bar{border-radius:var(--radius-md,2px) var(--radius-md,2px) 0 0;background:var(--ui-purple)}
.pa-bar[data-zero="1"]{border-radius:1px;margin-bottom:0;
  background:color-mix(in srgb, var(--ui-text-primary) 16%, transparent)}
.pa-flowsum{font-size:${TYPE.caption}px;color:var(--ui-text-secondary);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.pa-logwrap{margin:0;border:0;border-radius:0;overflow:hidden;position:relative}
.pa-sec{margin:8px 12px 0;border:1px solid var(--hx-line);border-radius:var(--radius-xl,3.2px);
  background:var(--hx-card);overflow:hidden}
.pa-sectitle{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:10px;
  row-gap:2px;padding:10px 12px 0}
.pa-sec > .pa-sectitle{padding:8px 12px 7px;border-bottom:1px solid var(--hx-line)}
.pa-sectitle > [data-slot="panel-section-label"]{grid-column:1;grid-row:1;color:var(--ui-text-primary);
  font-size:${TYPE.caption}px;font-weight:600;letter-spacing:.07em;line-height:1.3}
.pa-sectitle > .pa-secmeta{grid-column:1;grid-row:2;min-width:0;font-size:${TYPE.caption}px;line-height:1.35;
  color:var(--ui-text-tertiary)}
.pa-sectitle > .pa-secright{grid-column:2;grid-row:1 / span 2;justify-self:end;display:flex;align-items:center}
.pa-sec > .pa-chart{margin:0;border:0;border-radius:0;padding:6px 10px 8px}
.pa-date{position:relative;display:inline-flex;align-items:center;gap:2px;flex:none}
.pa-dateface{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:${TYPE.lead}px;height:28px;
  padding:0 11px;box-sizing:border-box;
  border-radius:var(--radius-xl,3.2px);border:1px solid var(--hx-line);background:var(--hx-field);
  color:var(--ui-text-secondary);cursor:pointer;white-space:nowrap;font-variant-numeric:tabular-nums}
.pa-dateface:hover{border-color:var(--ui-stroke-primary);color:var(--ui-text-primary)}
.pa-dateface:focus-visible{outline:1px solid var(--ui-accent);outline-offset:1px}
.pa-dateinput{position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;border:0;padding:0;
  pointer-events:none;background:transparent;color:transparent}
.pa-log{display:grid;gap:8px;padding:7px 8px;cursor:pointer;font-size:${TYPE.body}px;box-sizing:border-box;
  border-bottom:1px solid color-mix(in srgb, var(--ui-stroke-secondary) 60%, transparent);
  transition:${move('row', 'background-color, border-color')}}
.pa-log:last-child{border-bottom:0}
.pa-log:hover{background:var(--ui-row-hover-background)}
.pa-log:hover .pa-caret{color:var(--ui-text-secondary)}
.pa-log[data-open="1"]{background:var(--ui-row-open-background)}
.pa-log-head{display:grid;gap:8px;padding:0 8px;box-sizing:border-box;
  background:color-mix(in srgb, var(--ui-text-primary) 6%, transparent);
  border-bottom:1px solid var(--hx-line)}
.pa-cell{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pa-clamp{white-space:normal;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
  overflow:hidden;overflow-wrap:anywhere;line-height:15px}
.pa-titlecell{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:start;gap:6px;min-width:0}
.pa-badge{min-width:0;max-width:96px;overflow:hidden;text-overflow:ellipsis;
  border-radius:var(--radius-lg,2.4px);padding:4px 8px;line-height:1}
.pa-badge[data-tone="neutral"]{color:var(--ui-text-secondary)}
.pa-badge[data-tone="bad"]{color:color-mix(in srgb,var(--ui-red) 72%,var(--ui-text-primary))}
.pa-seg{height:28px;box-sizing:border-box;padding:2px;gap:2px;border-radius:var(--radius-xl,3.2px);
  border:1px solid var(--hx-line);background:var(--hx-field)}
.pa-seg button{height:22px;border-radius:var(--radius-lg,2.4px);padding:0 12px;font-size:${TYPE.lead}px;font-weight:500;
  line-height:1;color:var(--ui-text-secondary);box-shadow:none}
.pa-seg button:hover{color:var(--ui-text-primary)}
.pa-seg button[aria-pressed="true"]{background:color-mix(in srgb, var(--ui-text-primary) 11%, transparent);
  color:var(--ui-text-primary)}
.pa-strip{width:3px;height:16px;border-radius:var(--radius-md,2px);justify-self:start;align-self:start;margin-top:3px}
.pa-logscroll{container-type:inline-size;box-sizing:border-box}
.pa-logwrap[data-drawer="1"] .pa-logscroll{padding-right:clamp(270px,44%,430px)}
.pa-kv dt,.pa-drawer-sec>[data-slot="panel-section-label"]{color:var(--ui-text-secondary)}
.pa-kpi:focus-visible{outline:1px solid var(--ui-accent);outline-offset:1px}
.pa-clear-ask{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:6px 12px 8px;
  font-size:${TYPE.caption}px;line-height:1.45;color:var(--ui-text-secondary)}
.pa-clear-ask p{margin:0;flex:1 1 260px;min-width:0}
.pa-clear-note{padding:2px 12px 8px;font-size:${TYPE.caption}px;color:var(--ui-text-secondary)}
.pa-chronicle .pa-clear-ask,.pa-chronicle .pa-clear-note{margin:0;padding:12px 18px;gap:8px 12px;font-size:${TYPE.body}px;
  line-height:1.5;color:var(--ui-text-primary);border-bottom:1px solid var(--ui-stroke-tertiary);
  box-shadow:inset 3px 0 0 var(--ui-orange);background:color-mix(in srgb,var(--ui-orange) 6%,transparent)}
.pa-chronicle .pa-clear-note{box-shadow:inset 3px 0 0 var(--ui-accent);background:transparent}
@container (max-width: 470px){
.pa-act-row,.pa-act-axis{grid-template-columns:96px minmax(0,1fr)}
}
.pa-drawer{position:absolute;top:0;right:0;bottom:0;z-index:2;
  width:clamp(270px,44%,430px);box-sizing:border-box;
  display:flex;flex-direction:column;min-width:0;outline:none;
  border-left:1px solid var(--ui-stroke-primary);
  background:color-mix(in srgb, var(--ui-text-primary) 3%, var(--hx-raised));
  box-shadow:var(--shadow-lg);
  opacity:0;transform:translateX(100%);
  transition:${move('drawer', 'transform, opacity')}}
.pa-drawer[data-in="1"]{opacity:1;transform:none}
@media (prefers-reduced-motion: reduce){
  .pa-logwrap{transition:none}
  .pa-drawer{transition:none}
  .pa-log{transition:none}
  .pa-log .pa-caret{transition:none}
}
.pa-drawer-head{display:flex;align-items:flex-start;gap:8px;padding:10px 12px;
  background:color-mix(in srgb, var(--ui-text-primary) 4%, transparent);
  border-bottom:1px solid var(--hx-line)}
.pa-drawer-body{padding:10px 12px;scrollbar-width:thin;
  scrollbar-color:color-mix(in srgb, var(--ui-text-tertiary) 45%, transparent) transparent;
  mask-image:linear-gradient(to bottom,var(--ui-bg-elevated) calc(100% - 20px),transparent)}
.pa-drawer-sec{display:flex;flex-direction:column;gap:5px}
.pa-drawer-txt{margin:0;font-size:${TYPE.body}px;line-height:1.5;color:var(--ui-text-secondary)}
.pa-action{margin:0;border-left:2px solid var(--ui-accent);border-radius:0 var(--radius-lg,2.4px) var(--radius-lg,2.4px) 0;
  background:var(--ui-bg-quaternary);padding:6px 8px;font-size:${TYPE.body}px;line-height:1.5;
  color:var(--ui-text-primary)}
.pa-kv dd{margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.pa-quote{margin:0;padding:5px 7px;border-radius:var(--radius-lg,2.4px);background:var(--ui-inline-code-background);
  color:var(--ui-inline-code-foreground);font-size:${TYPE.caption}px;line-height:1.5;overflow-wrap:anywhere;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.pa-raw{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
  overflow-wrap:anywhere;word-break:break-word}
.pa-findlist{width:100%}
.pa-findlist > div{gap:0}
.pa-findlist [data-panel-row]{height:${H.findRow}px;min-height:${H.findRow}px;align-items:center;
  padding:0 2px;border-bottom:1px solid var(--ui-stroke-tertiary)}
.pa-findlist [data-panel-row]:last-child{border-bottom:0}
.pa-findlist [data-panel-row] .pa-drawer-txt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pa-findbody{padding:4px 4px 8px}
.pa-loader{margin:26px auto}
@container (max-width: 620px){
.pa-grid{grid-template-columns:3px 62px minmax(0,1.1fr) minmax(0,1.05fr) 12px !important}
.pa-c-todo{display:none !important}
}
@container (max-width: 470px){
.pa-grid{grid-template-columns:3px 62px minmax(0,1fr) 12px !important}
.pa-c-what{display:none !important}
}
@container (max-width: 360px){
.pa-grid{grid-template-columns:3px minmax(0,1fr) 12px !important}
.pa-c-time{display:none !important}
}
.pa-root{container-type:inline-size;${SURFACE}}
.pa-dot,.pa-ck-dot{display:inline-block;width:8px;height:8px;border-radius:var(--radius-md,2px);flex:0 0 auto}
.pa-selwrap{position:relative;display:inline-flex;flex:none}
.pa-sel{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 9px 0 11px;box-sizing:border-box;
  font:inherit;font-size:${TYPE.lead}px;border-radius:var(--radius-xl,3.2px);border:1px solid var(--hx-line);
  background:var(--hx-field);color:var(--ui-text-secondary);cursor:pointer;white-space:nowrap;
  max-width:220px;min-width:0}
.pa-sel:hover{background:var(--ui-control-hover-background);border-color:var(--ui-stroke-primary);color:var(--ui-text-primary)}
.pa-sel[data-open="1"]{border-color:color-mix(in srgb, var(--ui-accent) 55%, transparent);color:var(--ui-text-primary)}
.pa-sel:focus-visible{outline:1px solid var(--ui-accent);outline-offset:1px}
.pa-sel-txt{overflow:hidden;text-overflow:ellipsis}
.pa-sel-ico{flex:none;color:var(--ui-text-quaternary);transition:${move('hover', 'transform')}}
.pa-sel[data-open="1"] .pa-sel-ico{transform:rotate(180deg)}
.pa-sel-n{flex:none;font-size:${TYPE.micro}px;height:15px;padding:0 5px;border-radius:99px;display:inline-flex;
  align-items:center;font-variant-numeric:tabular-nums;
  background:color-mix(in srgb, var(--ui-accent) 18%, transparent);color:var(--ui-text-primary)}
@media (prefers-reduced-motion: reduce){.pa-sel-ico{transition:none}}
.pa-pop{position:absolute;z-index:20;top:32px;left:0;min-width:100%;padding:4px;box-sizing:border-box;
  border-radius:var(--radius-xl,3.2px);border:1px solid var(--ui-stroke-secondary);background:var(--hx-raised);
  box-shadow:var(--shadow-md);display:flex;flex-direction:column;gap:1px}
.pa-pop[data-align="right"]{left:auto;right:0}
.pa-opt{display:flex;align-items:center;gap:8px;width:100%;height:26px;padding:0 8px;box-sizing:border-box;
  border:0;background:none;font:inherit;font-size:${TYPE.body}px;color:var(--ui-text-secondary);cursor:pointer;
  border-radius:var(--radius-lg,2.4px);text-align:left;white-space:nowrap}
.pa-opt:hover{background:var(--ui-row-hover-background);color:var(--ui-text-primary)}
.pa-opt[data-on="1"]{color:var(--ui-text-primary);background:var(--ui-row-active-background)}
.pa-opt-n{margin-left:auto;font-size:${TYPE.caption}px;color:var(--ui-text-quaternary);
  font-variant-numeric:tabular-nums}
.pa-check{flex:none;width:14px;height:14px;border-radius:var(--radius-lg,2.4px);border:1px solid var(--hx-line);
  background:transparent;display:inline-flex;align-items:center;justify-content:center;color:transparent}
.pa-opt[data-on="1"] .pa-check{background:var(--ui-accent);border-color:var(--ui-accent);
  color:var(--dt-primary-foreground)}
.pa-pop-sep{height:1px;margin:3px 2px;background:var(--ui-stroke-secondary)}
.pa-cal{position:absolute;z-index:20;top:34px;left:0;padding:8px;border-radius:var(--radius-xl,3.2px);
  border:1px solid var(--ui-stroke-secondary);background:var(--hx-raised);
  box-shadow:var(--shadow-md)}
.pa-cal-head{display:flex;align-items:center;gap:4px;margin-bottom:6px}
.pa-cal-wd{display:grid;grid-template-columns:repeat(7,24px);gap:2px;margin-bottom:3px}
.pa-cal-wd span{font-size:${TYPE.micro}px;text-align:center;color:var(--ui-text-secondary)}
.pa-cal-grid{display:grid;grid-template-columns:repeat(7,24px);gap:2px}
.pa-cal-grid button{font:inherit;font-size:${TYPE.caption}px;height:22px;border:0;border-radius:var(--radius-lg,2.4px);background:none;
  color:var(--ui-text-secondary);cursor:pointer;padding:0}
.pa-cal-grid button:hover{background:var(--ui-control-hover-background);color:var(--ui-text-primary)}
.pa-cal-grid button[data-on="1"]{background:var(--ui-accent);color:var(--dt-primary-foreground)}
.pa-cal-grid button:focus-visible{outline:1px solid var(--ui-accent);outline-offset:1px}

.pa-chronicle{color:var(--ui-text-primary);padding-bottom:32px;box-sizing:border-box}
.pa-chronicle .pa-topbar{padding:28px var(--wa-gutter,28px) 0!important;align-items:flex-start!important}
.pa-chronicle .pa-title{font-size:${TYPE.heading}px!important;
  font-weight:600!important;letter-spacing:-.025em!important}
.pa-chronicle .pa-sec{margin:16px var(--wa-gutter,28px) 0;border-radius:var(--radius-xl,3.2px);background:transparent}
.pa-chronicle .pa-sectitle{padding:13px 18px!important;gap:6px 12px;background:transparent}
.pa-chronicle .pa-secmeta{color:var(--ui-text-secondary)}
.pa-chronicle .pa-seg{border:0;border-radius:var(--radius-lg,2.4px);background:transparent;padding:0;gap:5px;height:auto}
.pa-chronicle .pa-seg button{padding:6px 9px;height:30px;border:1px solid transparent;border-radius:var(--radius-lg,2.4px);
  font-size:${TYPE.caption}px;background:transparent;color:var(--ui-text-secondary)}
.pa-chronicle .pa-seg button:hover{background:var(--ui-row-hover-background)}
.pa-chronicle .pa-seg button[aria-pressed="true"]{border-color:transparent;
  background:var(--ui-row-active-background);color:var(--ui-text-primary)}
.ch-status{display:flex;flex-wrap:wrap;gap:6px;padding:16px 24px 0}
.ch-journal{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(280px,1fr);min-width:0;align-items:stretch;
  background:transparent}
.pa-root .ch-scroll{height:auto;max-height:${H.logScroll}px;overflow-y:auto;overflow-x:hidden;
  padding:15px 18px!important;scrollbar-width:thin;overscroll-behavior:contain;container-type:normal}
.pa-root .pa-log.ch-run{position:relative;isolation:isolate;display:grid;
  grid-template-columns:24px 64px minmax(0,1fr) auto 12px;align-items:center;gap:11px;
  height:${H.logRow}px;padding:4px 8px 4px 0;margin:0;border:0;border-radius:var(--radius-lg,2.4px);background:transparent;
  box-shadow:none;color:var(--ui-text-primary)}
.ch-run:before{content:'';position:absolute;left:14px;top:0;bottom:0;border-left:1px solid var(--ui-stroke-primary);
  pointer-events:none;z-index:-2}
.ch-run:first-child:before{top:50%}.ch-run:last-child:before{bottom:50%}
.ch-run:after{content:'';position:absolute;inset:2px 0;border:1px solid transparent;border-radius:var(--radius-lg,2.4px);
  pointer-events:none;z-index:-1}
.pa-root .ch-run[data-open="1"]:after{border-color:var(--ui-stroke-primary);background:var(--hx-raised)}
.pa-root .ch-run:hover:after{border-color:var(--ui-stroke-primary);background:var(--hx-raised)}
.pa-root .ch-run:focus-visible{outline:2px solid var(--ui-accent);outline-offset:-2px}
.ch-point{display:grid;place-items:center;width:24px;height:24px;box-sizing:border-box;border-radius:50%;
  border:1px solid var(--ui-stroke-primary);background:var(--wa-card,var(--dt-card));color:var(--ui-text-secondary)}
.ch-point[data-status="completed"]{border-color:color-mix(in srgb,var(--ui-green) 70%,var(--ui-stroke-primary))}
.ch-point[data-status="failed"]{border-color:color-mix(in srgb,var(--ui-red) 70%,var(--ui-stroke-primary))}
.ch-point[data-status="claimed"],.ch-point[data-status="running"]{
  border-color:color-mix(in srgb,var(--ui-orange) 70%,var(--ui-stroke-primary))}
.ch-time{display:grid;gap:2px;min-width:0;font-size:${TYPE.caption}px;color:var(--ui-text-secondary);
  font-variant-numeric:tabular-nums}
.ch-time time{font-family:var(--dt-font-mono,monospace);color:var(--ui-text-primary)}
.ch-time>span{font-size:${TYPE.caption}px;white-space:nowrap}
.ch-description{display:grid;gap:2px;min-width:0;align-content:center}
.ch-description strong{font-size:${TYPE.body}px;font-weight:600;line-height:1.4;color:var(--ui-text-primary)}
.ch-preview{display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;
  font-size:${TYPE.caption}px;line-height:1.5;overflow-wrap:anywhere;color:var(--ui-text-secondary)}
.ch-jobline{display:flex;align-items:baseline;gap:8px;min-width:0}
.ch-jobline>strong{min-width:0}
.ch-history{flex:0 0 auto;font-size:${TYPE.caption}px;line-height:1.4;color:var(--ui-text-secondary)}
.ch-facts{display:grid;gap:2px;justify-items:end;min-width:0;font-size:${TYPE.caption}px}
.ch-outcome{display:inline-flex;align-items:center;gap:6px;min-width:0;font-size:${TYPE.caption}px;
  line-height:1.4;color:var(--ui-text-primary)}
.ch-outcome-dot{display:inline-block;width:6px;height:6px;border-radius:50%;flex-shrink:0;
  background:var(--ui-text-secondary)}
.ch-outcome[data-status="completed"] .ch-outcome-dot{background:var(--ui-green)}
.ch-outcome[data-status="failed"] .ch-outcome-dot{background:var(--ui-red)}
.ch-outcome[data-status="claimed"] .ch-outcome-dot,.ch-outcome[data-status="running"] .ch-outcome-dot{
  background:var(--ui-orange)}
.ch-run-duration{font-family:var(--dt-font-mono,monospace);font-variant-numeric:tabular-nums;
  font-size:${TYPE.caption}px;color:var(--ui-text-secondary)}
.ch-caret{color:var(--ui-text-secondary)}
.ch-journal .pa-drawer{position:static;width:auto;height:auto;min-height:${H.logScroll}px;min-width:0;opacity:1;transform:none;
  transition:none;box-shadow:none;border-left:1px solid var(--ui-stroke-primary);background:transparent}
.ch-inspector .pa-drawer-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px 10px;
  padding:23px 24px 20px;border:0;background:transparent;flex-shrink:0}
.ch-inspector-label{display:flex;align-items:center;gap:8px;font-size:${TYPE.caption}px;
  line-height:1.4;color:var(--ui-text-secondary)}
.ch-inspector-label .codicon{font-size:${TYPE.lead}px}
.ch-inspector-title{grid-column:1/-1;min-width:0;overflow-wrap:anywhere;margin:0;
  font-size:calc(${TYPE.heading}px - 4px);font-weight:600;line-height:1.35;letter-spacing:-.02em;
  color:var(--ui-text-primary)}
.ch-inspector-head>.ch-outcome{grid-column:1/-1;margin-top:-5px}
.ch-journal .ch-inspector-body{display:flex;flex-direction:column;gap:0;padding:0 24px 22px;
  flex:none;min-height:0;overflow-y:visible;mask-image:none;color:var(--ui-text-primary)}
.ch-journal-main{min-width:0}.ch-journal-unused{padding:22px 24px;
  border-top:1px solid var(--ui-stroke-primary);color:var(--ui-text-primary)}
.ch-summary{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);gap:11px 12px;margin:0;
  padding:24px 0;border-top:1px solid var(--ui-stroke-primary);font-size:${TYPE.body}px;line-height:1.4}
.ch-summary dt{color:var(--ui-text-secondary);font-size:${TYPE.caption}px;white-space:normal}
.ch-summary dd{margin:0;text-align:right;color:var(--ui-text-primary);font-size:${TYPE.caption}px;
  overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.ch-error-section,.ch-duration-section{border-top:1px solid var(--ui-stroke-primary);padding:20px 0 24px}
.ch-error-section h3,.ch-duration-section h3{margin:0;font-size:${TYPE.body}px;line-height:1.5;font-weight:600;
  color:var(--ui-text-primary)}
.ch-error-preview{margin:10px 0 0;font-size:${TYPE.body}px;line-height:1.7;overflow-wrap:anywhere;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
  color:var(--ui-text-secondary)}
.ch-duration-section>p{margin:7px 0 0;font-size:${TYPE.caption}px;line-height:1.6;color:var(--ui-text-secondary)}
.ch-duration-list{display:grid;gap:13px;max-height:156px;overflow-y:auto;margin-top:17px;
  padding:1px 0;scrollbar-width:thin;overscroll-behavior:contain}
.ch-duration-row{display:grid;grid-template-columns:36px minmax(0,1fr) 54px;gap:8px;align-items:center;
  font-family:var(--dt-font-mono,monospace);font-size:${TYPE.caption}px;line-height:1.4;
  color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.ch-duration-row time{font-family:var(--dt-font-mono,monospace)}
.ch-duration-track{display:block;height:8px;background:var(--ui-stroke-tertiary);border-radius:var(--radius-md,2px);overflow:hidden}
.ch-duration-track i{display:block;height:100%;background:var(--ui-text-secondary);border-radius:var(--radius-md,2px)}
.ch-duration-row[data-status="completed"] .ch-duration-track i{background:var(--ui-green)}
.ch-duration-row[data-status="failed"] .ch-duration-track i{background:var(--ui-red)}
.ch-duration-row[data-status="running"] .ch-duration-track i,
.ch-duration-row[data-status="claimed"] .ch-duration-track i{background:var(--ui-orange)}
.ch-duration-value{text-align:right;font-family:var(--dt-font-mono,monospace);color:var(--ui-text-primary)}
.ch-trace-note{margin:0;border-top:1px solid var(--ui-stroke-primary);padding:20px 0;
  font-size:${TYPE.caption}px;line-height:1.7;color:var(--ui-text-secondary)}
.ch-technical{border-top:1px solid var(--ui-stroke-primary);padding-top:15px;min-width:0;
  color:var(--ui-text-primary);font-size:${TYPE.body}px;line-height:1.5}
.ch-technical>summary{cursor:pointer;min-height:26px;line-height:26px;color:var(--ui-text-secondary)}
.ch-technical>summary:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.ch-technical-body{display:flex;flex-direction:column;gap:20px;padding-top:16px;min-width:0}
.ch-inspector .pa-findlist [data-panel-row]{height:auto;min-height:${H.findRow}px;padding-top:6px;padding-bottom:6px}
.ch-inspector .pa-findlist .pa-badge{max-width:100%!important;white-space:normal;text-align:left}
.ch-inspector .pa-find:has(>.pa-findbody) [data-panel-row] .pa-drawer-txt{display:none}
.wa-shell .ch-technical .pa-findbody{padding:4px calc(var(--wa-pad) + 2px) 14px}
.ch-inspector .pa-kv{overflow-wrap:anywhere;color:var(--ui-text-primary)}
.ch-inspector .pa-kv dt,.ch-inspector .pa-drawer-sec>[data-slot="panel-section-label"]{
  color:var(--ui-text-secondary)}
.ch-inspector .pa-kv dd{color:var(--ui-text-primary)}
.ch-inspector .pa-raw{max-height:192px;background:var(--ui-inline-code-background);color:var(--ui-text-secondary);
  font-size:${TYPE.caption}px;line-height:1.6;overflow:auto}
.ch-inspector .pa-body-fail,.ch-inspector .pa-copy-fail{margin:6px 0;font-size:${TYPE.caption}px;
  line-height:1.5;color:var(--ui-text-primary);border-left:2px solid var(--ui-red);padding-left:8px}
.ch-inspector .pa-drawer-txt,.ch-inspector .pa-quote,.ch-inspector .pa-action{color:var(--ui-text-secondary)}
.ch-inspector .pa-action,.ch-inspector .pa-quote{background:var(--ui-inline-code-background)}
.ch-inspector .pa-badge[data-tone]{color:var(--ui-text-primary);background:var(--ui-inline-code-background)}
.ch-inspector-empty{height:${H.logScroll}px;box-sizing:border-box;border-left:1px solid var(--ui-stroke-primary);
  padding:24px;display:grid;align-content:center;justify-items:center;text-align:center;min-width:0;background:transparent}
@container (max-width:1080px){
  .ch-journal{grid-template-columns:minmax(0,1.8fr) minmax(265px,1fr)}
  .pa-root .pa-log.ch-run{grid-template-columns:28px 64px minmax(0,1fr) auto 10px;gap:9px}
  .ch-inspector .pa-drawer-head{padding:23px 20px 20px}.ch-journal .ch-inspector-body{padding:0 20px 22px}
}
@container (max-width:820px){
  .ch-journal{grid-template-columns:minmax(0,1fr)}
  .ch-journal .pa-drawer{height:auto;min-height:${H.drawer}px;border-left:0;border-top:1px solid var(--ui-stroke-primary)}
  .ch-inspector-empty{height:auto;min-height:110px;border-left:0;border-top:1px solid var(--ui-stroke-primary)}
}
@container (max-width:560px){
  .pa-chronicle .pa-topbar{padding:20px var(--wa-gutter,28px) 0!important}.pa-chronicle .pa-sec{margin:16px var(--wa-gutter,28px) 0}
  .pa-chronicle .pa-sectitle{grid-template-columns:minmax(0,1fr);padding:13px 14px!important}
  .pa-chronicle .pa-secright{grid-column:1;grid-row:3;justify-self:start}
  .ch-status{padding:14px 16px 0}.pa-logbars{flex-wrap:wrap;justify-content:flex-start}
  .pa-root .ch-scroll{padding:10px 13px!important}
  .pa-root .pa-log.ch-run{grid-template-columns:28px 76px minmax(0,1fr) 10px;
    height:${H.logRowNarrow}px;gap:2px 8px;padding:4px 8px 4px 0}
  .ch-point{grid-column:1;grid-row:1/span 2}.ch-time{grid-column:2;grid-row:1/span 2}
  .ch-description{grid-column:3;grid-row:1;gap:4px}.ch-caret{grid-column:4;grid-row:1/span 2}
  .ch-facts{grid-column:3;grid-row:2;display:flex;flex-wrap:wrap;align-items:center;gap:7px 12px}
  .ch-time>span{font-size:${TYPE.micro}px}.ch-description strong{font-size:${TYPE.body}px}
  .ch-preview{-webkit-line-clamp:1}.ch-history{font-size:${TYPE.micro}px}
}
@container (max-width:470px){
  .pa-chronicle .pa-seg{grid-auto-flow:row;grid-template-columns:repeat(2,minmax(0,1fr));height:auto;width:100%}
  .ch-status{display:block}.pa-chronicle .pa-filters-row>.pa-seg{flex:1 1 100%}
}
.pa-chronicle .pa-filters{flex-direction:row!important;flex-wrap:wrap;align-items:center;gap:14px!important;
  padding:16px var(--wa-gutter,28px) 0!important}
.pa-chronicle .pa-filters-row:first-child{flex:1 1 220px}
.pa-chronicle .pa-filters-row:last-child{flex:0 0 auto}
.ch-filters-advanced{min-width:0;flex:0 0 auto;font-size:${TYPE.caption}px;color:var(--ui-text-secondary)}
.ch-filters-advanced>summary{cursor:pointer;padding:7px 0;min-height:28px}
.ch-filters-advanced>summary:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.ch-filters-advanced[open]{flex:1 1 100%;padding-bottom:4px}
.ch-filters-advanced[open]>.pa-filters-row{padding:10px 0 2px}
.ch-filter-active{margin-left:10px;padding-left:10px;border-left:1px solid var(--ui-stroke-primary);color:var(--ui-text-primary)}
.pa-chronicle .pa-readline{padding:10px var(--wa-gutter,28px) 0!important}
.pa-chronicle .pa-sectitle{grid-template-columns:minmax(0,1fr) auto!important;align-items:center;gap:0 12px!important}
.pa-chronicle .pa-secright{grid-column:2;grid-row:1}
.pa-chronicle .pa-secmeta:empty{display:none}
.pa-chronicle .ch-status{padding:0;min-width:0}
.pa-chronicle .pa-secmeta:not(:empty){padding-top:7px}
@container (max-width:560px){.pa-chronicle .pa-filters{padding:14px var(--wa-gutter,28px) 0!important}
  .pa-chronicle .pa-readline{padding:10px var(--wa-gutter,28px) 0!important}
  .pa-chronicle .pa-filters-row:first-child{flex-basis:100%}
  .pa-chronicle .pa-filters-row:last-child{flex:1 1 100%}
  .pa-chronicle .pa-secright{grid-column:1;grid-row:3;padding-top:10px}}
.pa-root .pa-drawer-sec>[data-slot="panel-section-label"]{font-size:${TYPE.caption}px;line-height:1.4}
.pa-root.pa-health{
  display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);align-content:start;grid-auto-rows:max-content;gap:0;padding:0 var(--wa-gutter,28px) 32px;box-sizing:border-box}
.pa-health>:not(style){grid-column:1/-1;min-width:0}
.pa-health>.pa-topbar{padding:28px 0 0!important;align-items:flex-start!important}
.pa-health .pa-title{font-size:${TYPE.heading}px!important;font-weight:600!important;letter-spacing:-.025em!important;line-height:1.2!important}
.pa-health>.pa-readline{padding:10px 0 0!important;line-height:1.5}
.pa-health>.pa-stale{padding:10px 0 0!important;color:var(--ui-text-primary)!important;border-bottom:1px solid var(--ui-red)}
.pa-health>.pa-sec{margin:24px 0 0;border:0;border-top:1px solid var(--ui-stroke-primary);border-radius:0;background:transparent;overflow:visible}
.pa-health>.pa-sec:has(.pa-fr),.pa-health>.pa-sec:has(.pa-fr-none){border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-xl,3.2px);background:var(--hx-raised);overflow:hidden}
.pa-health>.pa-sec>.pa-sectitle{padding:16px 0 12px;gap:5px 16px;border-bottom:0;background:transparent;align-items:start}
.pa-health>.pa-sec:has(.pa-fr)>.pa-sectitle,.pa-health>.pa-sec:has(.pa-fr-none)>.pa-sectitle{padding:13px 18px;border-bottom:1px solid var(--hx-line)}
.pa-health .pa-sectitle>[data-slot="panel-section-label"],
.pa-health .pa-sectitle>.ch-status>[data-slot="panel-section-label"]{color:var(--ui-text-primary);font-size:${TYPE.body}px;font-weight:600;letter-spacing:0;text-transform:none;line-height:1.5}
.pa-health .pa-secmeta{color:var(--ui-text-secondary);white-space:normal!important;overflow:visible!important;line-height:1.5}
.pa-health .pa-fr{margin:12px 18px 16px;grid-template-columns:112px minmax(0,1fr);gap:20px}
.pa-health .pa-fr-body{display:grid;grid-template-columns:minmax(150px,1fr) minmax(0,1.5fr);
  grid-template-rows:auto auto;align-content:center;column-gap:24px}
.pa-health .pa-fr-head{grid-column:1;align-self:end}.pa-health .pa-fr-sum{grid-column:1;align-self:start}
.pa-health .pa-orbs{grid-column:2;grid-row:1/3;align-self:center;justify-content:flex-end}
.pa-health .pa-fr-cap{color:var(--ui-text-secondary)}.pa-health .pa-fr-body{gap:9px}
.pa-health .pa-orb[aria-pressed="true"]{background:var(--ui-row-active-background);border-color:var(--ui-stroke-primary)}
.pa-health .pa-orb{border-radius:var(--radius-lg,2.4px);background:transparent;padding:6px 9px}
.pa-health .pa-orb:hover{background:var(--ui-control-hover-background)}
.pa-health>.pa-kpis{padding:0!important;margin:20px 0 0;gap:0!important;border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-xl,3.2px);overflow:hidden}
.pa-health .pa-kpi,.pa-health .pa-kpi[data-state]{border:0;border-right:1px solid var(--ui-stroke-primary);border-radius:0;background:transparent;padding:12px 16px;overflow:visible}
.pa-health .pa-kpi:last-child{border-right:0}.pa-health .pa-kpi-lab{letter-spacing:.04em;color:var(--ui-text-secondary)}
.pa-health .pa-kpi>div:last-child{color:var(--ui-text-secondary)!important}.pa-health .pa-kpi:focus-visible{outline-offset:-2px}
.pa-health .pa-spark rect[fill="var(--ui-purple)"]{fill:var(--ui-text-secondary)}
.pa-health>.pa-filters{padding:0!important;margin:24px 0 0;gap:10px!important}
.pa-health .pa-filters-row>input{border-radius:var(--radius-lg,2.4px)!important}
.pa-health .pa-sel,.pa-health .pa-dateface{border-radius:var(--radius-lg,2.4px);background:transparent}
.pa-health .pa-filters .pa-seg{height:auto;border:0;border-radius:0;background:transparent;padding:0;gap:5px}
.pa-health .pa-filters .pa-seg button{height:30px;padding:6px 9px;border:1px solid transparent;border-radius:var(--radius-lg,2.4px);font-size:${TYPE.caption}px;background:transparent}
.pa-health .pa-filters .pa-seg button[aria-pressed="true"]{border-color:transparent;background:var(--ui-row-active-background);color:var(--ui-text-primary)}
.pa-health>.pa-sec>.pa-chart{padding:6px 0 8px;background:transparent}.pa-health .pa-bar{background:var(--ui-text-secondary)}
.pa-health .pa-bar-col[data-zero="0"] .pa-bar-day{border-top-color:var(--ui-text-secondary)}
.pa-health .pa-act{margin:0 0 8px;padding:7px 0;border:0;border-radius:0;background:transparent}
.pa-health .pa-act-name{color:var(--ui-text-primary)}
.pa-health .pa-tl-legend{margin:6px 0 12px;color:var(--ui-text-secondary);line-height:1.6}
.pa-health>.pa-legend{margin-top:20px;padding:16px 0 20px;border-top:1px solid var(--ui-stroke-primary);gap:8px 16px;align-items:flex-start}
.pa-health .pa-ck{flex-wrap:wrap}.pa-health .pa-ck-item{color:var(--ui-text-secondary)}
.pa-health .pa-act-scroll,.pa-health .pa-orbs{scrollbar-width:thin;scrollbar-color:var(--ui-stroke-primary) transparent}
@container(max-width:960px){.pa-root.pa-health{grid-template-columns:minmax(0,1fr)}
  .pa-health .pa-fr-body{display:flex}.pa-health .pa-orbs{justify-content:flex-start}
}
@container(max-width:560px){.pa-root.pa-health{padding:0 var(--wa-gutter,28px) 28px}.pa-health>.pa-topbar{padding-top:20px!important}
  .pa-health>.pa-sec{margin-top:20px}.pa-health .pa-fr{margin:10px 14px 14px;grid-template-columns:96px minmax(0,1fr);gap:12px}
  .pa-health>.pa-kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  .pa-health .pa-kpi,.pa-health .pa-kpi[data-state]{padding:10px 12px;border-right:0;border-bottom:1px solid var(--ui-stroke-primary)}
  .pa-health .pa-kpi:nth-child(odd){border-right:1px solid var(--ui-stroke-primary)}.pa-health .pa-kpi:last-child{grid-column:1/-1;border:0}
  .pa-health .pa-secright{grid-column:1;grid-row:3;justify-self:start}
  .pa-health .pa-act-row,.pa-health .pa-act-axis{grid-template-columns:96px minmax(0,1fr)}
  .pa-health .pa-filters-row>.pa-seg{flex:1 1 100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));width:100%}}
.pa-chronicle .pa-readline{line-height:1.5}
.pa-chronicle .pa-stale{margin:10px var(--wa-gutter,28px) 0;padding:8px 0!important;color:var(--ui-text-primary)!important;border-bottom:1px solid var(--ui-red)}
.pa-chronicle .pa-filters-row>input{border-radius:var(--radius-lg,2.4px)!important}.pa-chronicle .pa-sel,.pa-chronicle .pa-dateface{border-radius:var(--radius-lg,2.4px)}
.pa-chronicle .pa-clear-open{border:1px solid var(--ui-stroke-primary);border-radius:var(--radius-lg,2.4px);background:transparent;color:var(--ui-text-primary)}
.pa-chronicle .pa-clear-open:not(:disabled):hover{background:var(--ui-control-hover-background)}
.pa-chronicle .ch-time{gap:5px}.pa-chronicle .ch-description{gap:6px}
.pa-chronicle .ch-inspector-label,.pa-chronicle .ch-duration-section>p,.pa-chronicle .ch-trace-note{line-height:1.7}
.pa-chronicle .ch-scroll,.pa-chronicle .ch-inspector-body,.pa-chronicle .ch-duration-list,.pa-chronicle .pa-raw{scrollbar-width:thin;scrollbar-color:var(--ui-stroke-primary) transparent}
@container(max-width:560px){.pa-chronicle .pa-stale{margin:10px var(--wa-gutter,28px) 0}}
.pa-root button:focus-visible,.pa-root input:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.pa-tip{position:fixed;z-index:30;max-width:320px;padding:5px 7px;border-radius:var(--radius-xl,3.2px);
  background:var(--hx-raised);border:1px solid var(--ui-stroke-primary);color:var(--ui-text-primary);
  font-size:${TYPE.caption}px;line-height:1.45;box-shadow:var(--shadow-md);
  pointer-events:none}
`

const value = { fontSize: TYPE.body, lineHeight: 1.55, color: 'var(--ui-text-secondary)' }

const mono = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' }

const ell = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

const clamp2 = extra => ({
  minWidth: 0, overflow: 'hidden', display: '-webkit-box', WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2, whiteSpace: 'normal', overflowWrap: 'anywhere', lineHeight: '15px', ...extra
})

const cell = extra => ({ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...extra })

const headCell = extra => cell({
  fontSize: TYPE.micro, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase',
  color: 'var(--ui-text-secondary)', ...extra
})
const pad2 = n => String(n).padStart(2, '0')
const isoDay = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

const timeOf = iso => {
  const m = /T(\d{2}):(\d{2}):(\d{2})/.exec(String(iso || ''))
  return m ? `${m[1]}:${m[2]}:${m[3]}` : ''
}

const durationText = (ms, t) => {
  const n = ms
  if (typeof n !== 'number' || !Number.isFinite(n) || n < 0) return '—'
  return n < 1000 ? t('wd.ms', Math.round(n)) : t('wd.sec', (n / 1000).toFixed(1))
}

const latenessText = (s, t) => {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  if (n < 60) return t('wd.sec', Math.round(n))
  return t('wd.min', Math.round(n / 60))
}

const SORT_IDS = ['new', 'old', 'job', 'status']
const SORT_LABEL = { new: 'wd.sortNew', old: 'wd.sortOld', job: 'wd.sortJob', status: 'wd.sortStatus' }

const STATUS_BADGE = {
  completed: 'wd.badge.done', failed: 'wd.badge.failed', running: 'wd.badge.running',
  claimed: 'wd.badge.starting', unknown: 'wd.badge.unknown'
}
const DELIVERY_BADGE = {
  delivered: 'wd.badge.delivered', suppressed: 'wd.badge.silent', queued: 'wd.badge.queued',
  failed: 'wd.badge.delivFailed', none: 'wd.badge.none'
}
const ACTIVE_STATUS = ['running', 'claimed']
const statusTone = s => (s === 'failed' ? 'bad' : s === 'running' || s === 'claimed' ? 'warn' : '')
const deliveryTone = d => (d === 'failed' ? 'bad' : '')

const badgeVariant = tone => toneOf(tone).variant
const badge = (key, tone, extra) => jsx(Badge, {
  className: 'pa-badge', variant: badgeVariant(tone), 'data-tone': toneKey(tone), ...extra
}, key)

const WINDOW_FOR_PRESET = { today: '24h', '7d': '7d', '30d': '30d', all: 'all', custom: 'all' }
const WINDOW_LABEL = { '24h': 'wd.win24h', '7d': 'wd.win7d', '30d': 'wd.win30d', all: 'wd.winAll' }
const wdPlural = (n, one, many) => `${n} ${Number(n) === 1 ? one : many}`
const jobLabel = (entry, t) => entry?.name || `${t('wd.deletedJob')} (${String(entry?.id || '—')})`
const FINDING_MAP = {
  not_indexed: 'wd.map.notIndexed', wikilink: 'wd.map.wikilink', dup: 'wd.map.dup',
  drift: 'wd.map.drift', mirror: 'wd.map.mirror', identity: 'wd.map.identity',
  unresolvable: 'wd.map.unresolvable', isolated: 'wd.map.isolated',
  pages_down: 'wd.map.pagesDown', crash: 'wd.map.crash', evidence_store: 'wd.map.evidenceStore',
  evidence_stale: 'wd.map.evidenceStale', control_missing: 'wd.map.controlMissing',
  control_changed: 'wd.map.controlChanged', control_template: 'wd.map.controlTemplate',
  project_file_missing: 'wd.map.projectFileMissing', project_file_unreadable: 'wd.map.projectFileUnreadable',
  project_reregistered: 'wd.map.projectReregistered', index_stale: 'wd.map.indexStale',
  unsplit_ingest: 'wd.map.unsplitIngest', mcp_off: 'wd.map.mcpOff', commit_backlog: 'wd.map.commitBacklog',
  drift_crash: 'wd.map.driftCrash', harvest_unread: 'wd.map.harvestUnread', harvest_zstd: 'wd.map.harvestZstd',
  engine_copies: 'wd.map.engineCopies', other: 'wd.map.other'
}
const findingRaw = f => String(f.raw || f.detail || '')
const findingEnglish = (f, t) => t(FINDING_MAP[f.kind] || FINDING_MAP.other, f.data || {})
const FINDING_SHORT = {
  not_indexed: 'wa.metroShort.notIndexed', wikilink: 'wa.metroShort.wikilink', dup: 'wa.metroShort.dup',
  drift: 'wa.metroShort.drift', mirror: 'wa.metroShort.mirror', identity: 'wa.metroShort.identity',
  unresolvable: 'wa.metroShort.unresolvable', isolated: 'wa.metroShort.isolated',
  pages_down: 'wa.metroShort.pagesDown', crash: 'wa.metroShort.crash', evidence_store: 'wa.metroShort.evidenceStore',
  evidence_stale: 'wa.metroShort.evidenceStale', control_missing: 'wa.metroShort.controlMissing',
  control_changed: 'wa.metroShort.controlChanged', control_template: 'wa.metroShort.controlTemplate',
  project_file_missing: 'wa.metroShort.projectFileMissing', project_file_unreadable: 'wa.metroShort.projectFileUnreadable',
  project_reregistered: 'wa.metroShort.projectReregistered', index_stale: 'wa.metroShort.indexStale',
  unsplit_ingest: 'wa.metroShort.unsplitIngest', mcp_off: 'wa.metroShort.mcpOff',
  commit_backlog: 'wa.metroShort.commitBacklog', drift_crash: 'wa.metroShort.driftCrash',
  harvest_unread: 'wa.metroShort.harvestUnread', harvest_zstd: 'wa.metroShort.harvestZstd',
  engine_copies: 'wa.metroShort.engineCopies', other: 'wa.metroShort.other'
}
const findingShort = (f, t) => t(FINDING_SHORT[f.kind] || FINDING_SHORT.other, f.data || {})
const capitalFirst = text => String(text || '').replace(/^\s*\S/, c => c.toUpperCase())

function useHealthPolling(load, ms) {
  const [state, setState] = useState({ data: null, error: null, busy: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    let inFlight = false
    const run = async () => {
      if (!alive || inFlight) return
      inFlight = true
      setState(s => ({ ...s, busy: true }))
      try {
        const data = await load()
        if (alive) setState({ data, error: null, busy: false })
      } catch (error) {
        if (alive) setState(s => ({ data: s.data, error, busy: false }))
      } finally {
        inFlight = false
      }
    }
    void run()
    const handle = setInterval(run, ms)
    return () => {
      alive = false
      clearInterval(handle)
    }
  }, [ms, tick])
  return { ...state, refresh: () => setTick(t => t + 1) }
}

function RefreshButton({ onClick, labelText, busy }) {
  return jsx(Button, {
    className: 'pa-icon',
    variant: 'ghost',
    size: 'icon-sm',
    'aria-label': labelText,
    'data-busy': busy ? '1' : '0',
    ...hoverTip(labelText),
    onClick,
    children: jsx('svg', {
      width: 14, height: 14, viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false',
      fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round',
      children: jsxs('g', {
        children: [
          jsx('path', { d: 'M13.5 8a5.5 5.5 0 1 1-1.62-3.9' }),
          jsx('path', { d: 'M13.6 2.4v2.6h-2.6' })
        ]
      })
    })
  })
}

function Chevron({ size = 10, className = 'pa-sel-ico', style }) {
  return jsx('svg', {
    className,
    width: size,
    height: size,
    viewBox: '0 0 12 12',
    style,
    'aria-hidden': 'true',
    focusable: 'false',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    children: jsx('path', { d: 'M3 4.5 6 7.5 9 4.5' })
  })
}

function CheckMark({ mixed }) {
  return jsx('svg', {
    width: 9,
    height: 9,
    viewBox: '0 0 12 12',
    'aria-hidden': 'true',
    focusable: 'false',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    children: mixed ? jsx('path', { d: 'M3 6h6' }) : jsx('path', { d: 'M2.6 6.2 4.9 8.6 9.4 3.4' })
  })
}

const OPEN_POPS = new Set()

function Select({ id, labelText, valueText, count, options, onPick, multi, align, selectedId }) {
  const [open, setOpen] = useState(false)
  const onArrow = e => {
    const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
    if (!keys.includes(e.key)) return
    const items = [...e.currentTarget.querySelectorAll('[role="option"]')]
    if (!items.length) return
    e.preventDefault()
    const at = items.indexOf(document.activeElement)
    const last = items.length - 1
    const to = e.key === 'Home' ? 0 : (e.key === 'End' ? last
      : (e.key === 'ArrowDown' ? Math.min(last, at + 1) : Math.max(0, at - 1)))
    items[to].focus()
  }
  useEffect(() => {
    if (!open) return undefined
    OPEN_POPS.add(id)
    const onKey = e => { if (e.key === 'Escape') setOpen(false) }
    const onDoc = e => {
      const wrap = e.target?.closest?.('.pa-selwrap')
      if (!wrap || wrap.getAttribute('data-sel') !== id) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDoc)
    return () => {
      OPEN_POPS.delete(id)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDoc)
    }
  }, [open, id])
  return jsxs('span', {
    className: 'pa-selwrap',
    'data-sel': id,
    children: [
      jsx('button', {
        type: 'button',
        className: 'pa-sel',
        'data-open': open ? '1' : '0',
        'aria-label': `${labelText}: ${valueText}`,
        'aria-haspopup': 'listbox',
        'aria-expanded': open ? 'true' : 'false',
        ...hoverTip(labelText),
        onClick: () => setOpen(o => !o),
        children: [
          jsx('span', { className: 'pa-sel-txt', children: valueText }, 'txt'),
          count ? jsx('span', { className: 'pa-sel-n', children: String(count) }, 'n') : null,
          jsx(Chevron, {}, 'ico')
        ]
      }, 'face'),
      open
        ? jsx('div', {
            className: 'pa-pop',
            role: 'listbox',
            'aria-label': labelText,
            'aria-multiselectable': multi ? 'true' : undefined,
            'data-align': align === 'right' ? 'right' : 'left',
            onKeyDown: onArrow,
            children: options.map(o => {
              const on = multi ? Boolean(o.on) : o.id === selectedId
              const trail = multi ? (o.n ? String(o.n) : '') : ''
              return jsxs('button', {
                type: 'button',
                className: 'pa-opt',
                role: 'option',
                'data-on': on ? '1' : '0',
                'aria-selected': on ? 'true' : 'false',
                onClick: () => { onPick(o.id); if (!multi) setOpen(false) },
                children: [
                  multi
                    ? jsx('span', {
                        className: 'pa-check',
                        children: jsx(CheckMark, { mixed: Boolean(o.mixed) })
                      }, 'box')
                    : null,
                  jsx('span', { className: 'pa-sel-txt', children: o.text }, 'txt'),
                  jsx('span', {
                    className: 'pa-opt-n',
                    children: multi ? trail : (on ? jsx(CheckMark, {}) : '')
                  }, 'n')
                ]
              }, o.id)
            })
          }, 'pop')
        : null
    ]
  })
}

function flowDays(rows, now) {
  const today = isoDay(new Date(now * 1000))
  const first = rows.reduce((min, r) => (r.date && r.date < min ? r.date : min), today)
  const span = Math.round((Date.parse(today) - Date.parse(first)) / 86400000) + 1
  return Math.min(MAX_DAYS, Math.max(DAYS, span || DAYS))
}

function dailyBuckets(rows, now, days = DAYS) {
  const dayMs = 86400000
  const today = new Date(now * 1000)
  today.setHours(0, 0, 0, 0)
  const buckets = []
  for (let i = days - 1; i >= 0; i -= 1) {
    const day = new Date(today.getTime() - i * dayMs)
    buckets.push({ iso: isoDay(day), day: pad2(day.getDate()), n: 0 })
  }
  const index = new Map(buckets.map(b => [b.iso, b]))
  rows.forEach(r => {
    const bucket = r.date ? index.get(r.date) : null
    if (bucket) bucket.n += 1
  })
  return buckets
}

function TopBar({ t, onRefresh, busy }) {
  return jsx('div', {
    className: 'pa-topbar',
    style: { display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, padding: '0 12px', marginBottom: -28 },
    children: jsx(RefreshButton, { labelText: t('wd.refresh'), onClick: onRefresh, busy })
  })
}

function stampLine({ t, data }) {
  if (!data?.generatedAt) return null
  const win = WINDOW_LABEL[data.window] ? t(WINDOW_LABEL[data.window]) : String(data.window || '')
  const parts = [
    t('wd.readAt', timeOf(data.generatedAt)),
    t('wd.window', win, (data.runs || []).length)
  ]
  if (data.truncated) parts.push(t('wd.truncated', data.cap))
  return jsx('div', {
    className: 'pa-readline',
    style: { padding: '5px 12px 0', fontSize: TYPE.caption, color: 'var(--ui-text-secondary)' },
    children: parts.join(' · ')
  })
}

function Ring({ size, fraction, tone, children }) {
  const r = (size - 12) / 2
  const circumference = 2 * Math.PI * r
  const cut = Math.max(0, Math.min(1, fraction))
  return jsxs('span', { className: 'pa-ring', style: { width: size, height: size }, children: [
    jsx('svg', {
      width: size, height: size, viewBox: `0 0 ${size} ${size}`, 'aria-hidden': 'true',
      focusable: 'false',
      children: [
        jsx('circle', { cx: size / 2, cy: size / 2, r, fill: 'none',
          stroke: 'var(--ui-stroke-secondary)', strokeWidth: 10 }, 'track'),
        jsx('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: toneOf(tone).color,
          className: 'pa-ring-arc',
          strokeWidth: 10, strokeLinecap: 'round', strokeDasharray: circumference,
          strokeDashoffset: circumference * (1 - cut),
          transform: `rotate(-90 ${size / 2} ${size / 2})` }, 'arc')
      ]
    }, 'svg'),
    jsx('span', { className: 'pa-ring-mid', children }, 'mid')
  ] })
}

function cycleOf(job, now) {
  const last = Date.parse(job?.last_run_at || '')
  const next = Date.parse(job?.next_run_at || '')
  if (!Number.isFinite(last) || !Number.isFinite(next) || next <= last) return null
  const fraction = (now - last) / (next - last)
  return { last, next, fraction, overdue: now > next,
           ageS: Math.max(0, Math.round((now - last) / 1000)) }
}

function agoText(seconds, t) {
  if (!Number.isFinite(seconds)) return '—'
  if (seconds < 90) return t('wd.secs', Math.round(seconds))
  return t('wd.mins', Math.round(seconds / 60))
}

function agoShort(seconds, t) {
  if (!Number.isFinite(seconds)) return '—'
  if (seconds < 90) return t('wd.unitShort', Math.round(seconds), t('wd.unitSec'))
  if (seconds < 5400) return t('wd.unitShort', Math.round(seconds / 60), t('wd.unitMin'))
  return t('wd.unitShort', Math.round(seconds / 3600), t('wd.unitHour'))
}

const liveInScope = (data, present) => (data?.registry || [])
  .filter(job => job.live && present.includes(job.id))

function Freshness({ t, data, shown, present, nameOf, onPick, picked = [] }) {
  const now = Date.parse(data?.generatedAt || '') || Date.now()
  const cycles = liveInScope(data, present).map(job => ({ job, cycle: cycleOf(job, now) }))
  const newestRun = shown.reduce((best, r) => (typeof r.at_ts === 'number' && r.at_ts * 1000 > best
    ? r.at_ts * 1000 : best), 0)
  const soonest = cycles.filter(e => e.cycle)
    .reduce((best, entry) => (!best || entry.cycle.next < best.cycle.next ? entry : best), null)
  const fleetCycle = soonest && newestRun
    ? { ...soonest.cycle, fraction: (now - newestRun) / (soonest.cycle.next - newestRun) }
    : null
  const failed = shown.filter(r => r.status === 'failed').length
  const silent = shown.filter(r => r.silent).length
  const delivered = shown.filter(r => r.delivery === 'delivered').length
  if (!cycles.length) {
    return jsx('div', { className: 'pa-fr-none', style: { padding: '6px 12px 10px', fontSize: TYPE.body,
      color: 'var(--ui-text-tertiary)' }, children: t('wd.frNone') }, 'none')
  }
  const tone = fleetCycle?.overdue ? (failed ? 'bad' : 'warn') : 'neutral'
  const untilNext = soonest ? Math.round((soonest.cycle.next - now) / 60000) : 0
  const head = !fleetCycle ? t('wd.frNone')
    : (fleetCycle.overdue
      ? t('wd.frOverdue', Math.max(1, Math.round((now - soonest.cycle.next) / 60000)))
      : t('wd.frClean', untilNext))
  return jsxs('div', { className: 'pa-fr', style: { minHeight: H.freshness }, children: [
    jsxs('span', { className: 'pa-ringcol', children: [
      jsx(Ring, {
        size: 88, fraction: fleetCycle ? fleetCycle.fraction : 0, tone,
        children: jsx('b', { children: agoShort(fleetCycle ? (now - newestRun) / 1000 : NaN, t) }, 'v')
      }, 'ring'),
      jsx('span', { className: 'pa-fr-cap', children: t('wd.frSince') }, 'k')
    ] }, 'col'),
    jsxs('div', { className: 'pa-fr-body', children: [
      jsx('div', { className: 'pa-fr-head', children: head }, 'head'),
      jsx('div', { className: 'pa-fr-sum', children: t('wd.frSummary', failed, silent, delivered) }, 'sum'),
      jsxs('div', { className: 'pa-orbs', children: cycles.map(entry => {
        const jobFailed = String(entry.job.last_status || '') === 'failed'
        return jsxs(Button, {
          className: 'pa-orb',
          size: 'sm',
          variant: 'ghost',
          'aria-pressed': picked.length === 1 && picked[0] === entry.job.id,
          ...hoverTip(entry.cycle
            ? `${nameOf(entry.job.id)} — ${t('wd.frPick')}`
            : `${nameOf(entry.job.id)} — ${t('wd.frNoCycle')}`),
          onClick: () => onPick(entry.job.id),
          children: [
            jsx(Ring, {
              size: 24, fraction: entry.cycle ? entry.cycle.fraction : 0,
              tone: entry.cycle?.overdue ? (jobFailed ? 'bad' : 'warn') : 'neutral',
              children: null
            }, 'r'),
            jsxs('span', { children: [
              jsx('span', { className: 'n', children: nameOf(entry.job.id) }, 'n'),
              jsx('span', { className: 'm',
                children: entry.cycle ? agoText(entry.cycle.ageS, t) : t('wd.frNoRing') }, 'm')
            ] }, 't')
          ]
        }, entry.job.id)
      }) }, 'orbs')
    ] }, 'body')
  ] })
}

function Spark({ series, tone }) {
  const max = Math.max(1, ...series)
  const slot = 100 / Math.max(1, series.length)
  const ink = tone ? toneOf(tone).color : 'var(--ui-purple)'
  return jsx('svg', {
    className: 'pa-spark', viewBox: '0 0 100 16', preserveAspectRatio: 'none',
    'aria-hidden': 'true', focusable: 'false',
    children: series.map((v, i) => {
      const h = v ? 4 + (v / max) * 12 : 1
      return jsx('rect', {
        x: (i * slot + slot * 0.18).toFixed(2), width: (slot * 0.64).toFixed(2),
        y: (16 - h).toFixed(2), height: h.toFixed(2),
        fill: v ? ink : 'var(--ui-stroke-secondary)'
      }, `b${i}`)
    })
  }, 'spark')
}

function Delta({ t, now, before, basis, better, approx }) {
  if (before === null || before === undefined || !Number.isFinite(Number(before))) return null
  const diff = Number(now) - Number(before)
  const dir = diff > 0 ? 'up' : (diff < 0 ? 'down' : 'flat')
  const tone = approx || dir === 'flat' || !better ? 'flat' : (dir === better ? 'good' : 'bad')
  const tip = approx ? t('wd.deltaApprox', basis, before) : t('wd.deltaTip', basis, before)
  return jsxs('span', {
    className: 'pa-delta',
    'data-dir': tone,
    'data-approx': approx ? 'true' : undefined,
    'aria-label': tip,
    ...hoverTip(tip),
    children: [
      approx ? jsx('span', { className: 'pa-delta-approx', children: '≈' }, 'x') : null,
      jsx('i', { className: 'pa-delta-a', children: diff ? (diff > 0 ? '▲' : '▼') : '=' }, 'a'),
      diff ? jsx('span', { children: String(Math.abs(diff)) }, 'n') : null
    ]
  }, 'delta')
}

function KpiRow({ t, shown, trend }) {
  const failed = shown.filter(r => r.status === 'failed').length
  const silent = shown.filter(r => r.silent).length
  const delivered = shown.filter(r => r.delivery === 'delivered').length
  const withFind = shown.filter(r => Number(r.findings_count) > 0).length
  const buckets = trend?.buckets || []
  const series = key => buckets.map(b => Number(b[key]) || 0)
  const prevOf = key => (trend?.prev ? Number(trend.prev[key]) || 0 : null)
  const findingsSeries = buckets.map(b => {
    const from = Date.parse(b.iso) / 1000
    const to = from + (trend?.bucket_hours || 1) * 3600
    return shown.filter(r => {
      if (!(Number(r.findings_count) > 0) || typeof r.at_ts !== 'number') return false
      return r.at_ts >= from && r.at_ts < to
    }).length
  })
  const cards = [
    { lab: t('wd.kpi.runs'), fig: String(shown.length), hint: t('wd.kpi.runsHint', shown.length),
      series: series('runs'), prev: prevOf('runs') },
    { lab: t('wd.kpi.failed'), fig: String(failed), hint: t('wd.kpi.failedHint'),
      tone: failed ? 'bad' : '', series: series('failed'), prev: prevOf('failed'), better: 'down' },
    { lab: t('wd.kpi.silent'), fig: String(silent), hint: t('wd.kpi.silentHint'),
      series: series('silent'), prev: prevOf('silent'), better: 'down' },
    { lab: t('wd.kpi.delivered'), fig: String(delivered), hint: t('wd.kpi.deliveredHint'),
      series: series('delivered'), prev: prevOf('delivered'),
      better: 'up' },
    { lab: t('wd.kpi.withFindings'), fig: String(withFind), hint: t('wd.kpi.withFindingsHint'),
      tone: withFind ? 'warn' : '', series: findingsSeries, prev: null, better: 'down' }
  ]
  return jsx('div', {
    className: 'pa-kpis',
    style: {
      display: 'grid', gap: 8, padding: '9px 12px 0',
      gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))'
    },
    children: cards.map((c, i) => jsxs('div', {
      className: 'pa-kpi',
      'data-state': Number(c.fig) > 0 && c.tone ? toneKey(c.tone) : undefined,
      style: { minHeight: H.kpi },
      tabIndex: 0,
      role: 'group',
      'aria-label': c.prev === null && c.series.length
        ? `${c.lab}: ${c.fig} — ${c.hint} · ${t('wd.deltaNone')}`
        : `${c.lab}: ${c.fig} — ${c.hint}`,
      ...hoverTip(c.prev === null && c.series.length
        ? `${c.lab}: ${c.fig} — ${c.hint} · ${t('wd.deltaNone')}`
        : `${c.lab}: ${c.fig} — ${c.hint}`),
      children: [
        jsxs('div', {
          className: 'pa-kpi-lab',
          style: { height: 14, overflow: 'hidden' },
          children: [
            c.tone
              ? jsx('span', {
                  className: 'pa-dot',
                  'data-tone': toneKey(c.tone),
                  style: { background: toneOf(c.tone).color, marginRight: 4, verticalAlign: 'middle' }
                }, 'dot')
              : null,
            jsx('span', { children: c.lab }, 'lab')
          ]
        }, 'l'),
        jsxs('div', {
          style: { display: 'flex', alignItems: 'baseline' },
          children: [
            jsx('span', {
              className: 'pa-kpi-fig',
              style: {
                fontSize: TYPE.figure, fontWeight: 650, lineHeight: '30px', letterSpacing: -0.5,
                color: 'var(--ui-text-primary)',
                fontVariantNumeric: 'tabular-nums'
              },
              children: c.fig
            }, 'f'),
            jsx(Delta, { t, now: Number(c.fig), before: c.prev, basis: trend?.prev_basis || '',
              better: c.better, approx: trend?.trend_truncated === true }, 'd')
          ]
        }, 'f'),
        c.series?.length ? jsx(Spark, { series: c.series, tone: c.tone }, 's') : null
      ]
    }, `${c.lab}-${i}`))
  })
}

const activityLanes = (trend, present) => Object.entries(trend?.per_job || {})
  .filter(([jid, cells]) => present.includes(jid) && cells.some(c => c.runs > 0))
  .sort((a, b) => b[1].reduce((n, c) => n + c.runs, 0) - a[1].reduce((n, c) => n + c.runs, 0))

const bucketLabel = (iso, hours, spanHours) => {
  const when = new Date(iso)
  const day = `${pad2(when.getDate())}.${pad2(when.getMonth() + 1)}`
  const clock = `${pad2(when.getHours())}:${pad2(when.getMinutes())}`
  if (Number(hours) >= 24) return day
  return Number(spanHours) > 24 ? `${day} ${clock}` : clock
}

function ActivityCard({ t, trend, present, nameOf }) {
  const approx = trend?.trend_truncated === true ? '≈' : ''
  const lanes = activityLanes(trend, present)
  if (!lanes.length) {
    return jsx('div', { className: 'pa-act-none', style: { padding: '6px 12px 10px', fontSize: TYPE.body,
      color: 'var(--ui-text-tertiary)' }, children: t('wd.actNone') }, 'none')
  }
  const shownLanes = lanes.slice(0, ACT_LANES)
  const edge = lanes[0][1]
  const hours = trend?.bucket_hours
  const spanHours = (Number(hours) || 0) * (trend?.buckets || []).length
  return jsxs('div', { children: [
    jsxs('div', { className: 'pa-act',
      children: [jsx('div', {
        className: 'pa-act-scroll',
        style: { maxHeight: H.activity, overflowY: 'auto', overscrollBehavior: 'contain' },
        children: shownLanes.map(([jid, cells]) => jsxs('div', {
        className: 'pa-act-row',
        children: [
          jsxs('span', { className: 'pa-act-name', ...hoverTip(nameOf(jid)), children: [
            jsx('span', { className: 'pa-act-label', children: nameOf(jid) }, 'label'),
            jsx('b', { className: 'pa-act-count', children: approx + cells.reduce((n, c) => n + c.runs, 0) }, 'count')
          ] }, 'n'),
          jsx('span', { className: 'pa-act-cells',
            style: { gridTemplateColumns: `repeat(${cells.length}, 1fr)` },
            children: cells.map(cell => jsx('span', {
              className: 'pa-act-cell',
              'data-tone': cell.failed ? 'bad' : (cell.silent ? 'warn' : (cell.delivered ? 'delivered'
                : 'none')),
              ...hoverTip(t('wd.actCell', bucketLabel(cell.iso, hours, spanHours), cell.runs))
            }, `${jid}-${cell.iso}`)) }, 'c')
        ]
      }, jid)) }, 'scroll'),
      jsxs('div', { className: 'pa-act-axis', 'aria-hidden': 'true', children: [
        jsx('span', {}, 'pad'),
        jsxs('span', { children: [
          jsx('span', { children: bucketLabel(edge[0].iso, hours, spanHours) }, 'a'),
          jsx('span', { children: bucketLabel(edge[edge.length - 1].iso, hours, spanHours) }, 'b')
        ] }, 'x')
      ] }, 'axis')] }, 'lanes'),
    lanes.length > shownLanes.length
      ? jsx('div', { className: 'pa-tl-legend', children: t('wd.actMore', lanes.length - shownLanes.length) }, 'more')
      : null
  ] })
}

function FilterBar({ t, all, filters, setFilters, present, nameOf }) {
  const counts = new Map()
  all.forEach(r => counts.set(r.job_id, (counts.get(r.job_id) || 0) + 1))
  const picked = filters.jobs
  const jobFace = picked.length === 0
    ? t('wd.allJobs')
    : picked.length === 1 ? nameOf(picked[0]) : t('wd.jobsN', picked.length)
  const jobOptions = [{
    id: '*', text: t('wd.allJobs'), on: picked.length === 0, mixed: picked.length > 0, n: all.length
  }].concat(present.map(jid => ({
    id: jid,
    text: nameOf(jid),
    on: picked.includes(jid),
    n: counts.get(jid) || 0
  })))
  const pickJob = id => setFilters(f => (id === '*'
    ? { ...f, jobs: [] }
    : { ...f, jobs: f.jobs.includes(id) ? f.jobs.filter(k => k !== id) : f.jobs.concat(id) }))

  const presets = [['today', t('wd.today')], ['7d', t('wd.days7')], ['30d', t('wd.days30')], ['all', t('wd.all')]]
  const inputStyle = {
    font: 'inherit', fontSize: TYPE.lead, padding: '0 11px', borderRadius: 'var(--radius-xl,3.2px)',
    border: '1px solid var(--hx-line)',
    background: 'var(--hx-field)', color: 'var(--ui-text-primary)'
  }
  const filtering = Boolean(filters.q || filters.jobs.length || filters.start || filters.end)
  const rowStyle = { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }
  return jsxs('div', {
    className: 'pa-filters',
    style: { display: 'flex', flexDirection: 'column', gap: 6, padding: '9px 12px 0' },
    children: [
      jsxs('div', {
        className: 'pa-filters-row',
        style: rowStyle,
        children: [
          jsx('input', {
            value: filters.q,
            placeholder: t('wd.filterPlaceholder'),
            'aria-label': t('wd.filterPlaceholder'),
            onChange: e => setFilters(f => ({ ...f, q: e.target.value })),
            style: { ...inputStyle, flex: '1 1 150px', minWidth: 0, height: 28, boxSizing: 'border-box' }
          }, 'q'),

          filtering
            ? jsx(Button, {
                className: 'pa-clearall',
                variant: 'outline',
                size: 'sm',
                onClick: () => setFilters({ q: '', jobs: [], preset: 'all', start: '', end: '' }),
                children: t('wd.filterClear')
              }, 'clear')
            : null
        ]
      }, 'row-q'),
      jsxs('details', { className: 'ch-filters-advanced', children: [
        jsxs('summary', { children: [
          jsx('span', { children: t('wd.journalFilters') }, 'label'),
          filters.jobs.length || filters.preset !== 'all' ? jsx('span', {
            className: 'ch-filter-active', children: t('wd.journalFiltersActive') }, 'active') : null
        ] }, 'summary'),
        jsxs('div', { className: 'pa-filters-row', style: rowStyle, children: [
          jsx(Select, {
            id: 'jobs', labelText: t('wd.jobsSelect'), valueText: jobFace,
            count: picked.length > 1 ? picked.length : 0, options: jobOptions,
            onPick: pickJob, multi: true
          }, 'jobs'),
          jsx(SegmentedControl, {
            className: 'pa-seg',
            onChange: id => setFilters(f => ({ ...f, preset: id, ...presetRange(id) })),
            options: presets.map(([id, label]) => ({ id, label })),
            value: filters.preset
          }, 'presets'),
          jsx(DateField, {
            t, side: 'start', value: filters.start,
            onChange: v => setFilters(f => ({ ...f, preset: 'custom', start: v }))
          }, 'startInput'),
          jsx('span', { style: { ...value, color: 'var(--ui-text-secondary)' }, children: '–' }, 'dash'),
          jsx(DateField, {
            t, side: 'end', value: filters.end,
            onChange: v => setFilters(f => ({ ...f, preset: 'custom', end: v }))
          }, 'endInput')
        ] }, 'row-dates')
      ] }, 'advanced')
    ]
  })
}

function presetRange(preset) {
  if (preset === 'all') return { start: '', end: '' }
  const now = new Date()
  const to = isoDay(now)
  if (preset === 'today') return { start: to, end: to }
  const back = new Date(now)
  back.setDate(back.getDate() - (preset === '7d' ? 6 : 29))
  return { start: isoDay(back), end: to }
}

function DateField({ t, side, value: iso, onChange }) {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState(() => (iso ? new Date(`${iso}T12:00:00`) : new Date()))
  const label = side === 'start' ? t('wd.startDate') : t('wd.endDate')
  const faceLabel = side === 'start' ? t('wd.startFace') : t('wd.endFace')
  const face = iso || faceLabel

  useEffect(() => {
    if (!open) return undefined
    const onKey = e => { if (e.key === 'Escape') setOpen(false) }
    const onDoc = e => { if (!e.target?.closest?.('.pa-date')) setOpen(false) }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDoc)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDoc)
    }
  }, [open])

  const year = view.getFullYear()
  const month = view.getMonth()
  const lead = (new Date(year, month, 1).getDay() + 6) % 7
  const days = new Date(year, month + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < lead; i += 1) cells.push(jsx('span', {}, `pad-${i}`))
  for (let d = 1; d <= days; d += 1) {
    const dayIso = isoDay(new Date(year, month, d))
    cells.push(jsx('button', {
      type: 'button',
      'data-on': iso === dayIso ? '1' : '0',
      'aria-label': dayIso,
      onClick: () => { onChange(dayIso); setOpen(false) },
      children: String(d)
    }, dayIso))
  }

  const calArrow = e => {
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 7, ArrowUp: -7 }[e.key]
    if (!step) return
    const list = [...e.currentTarget.querySelectorAll('button')]
    const at = list.indexOf(e.target)
    if (at < 0) return
    e.preventDefault()
    list[Math.min(list.length - 1, Math.max(0, at + step))].focus()
  }

  return jsxs('span', {
    className: 'pa-date',
    children: [
      jsx('button', {
        type: 'button',
        className: 'pa-dateface',
        'aria-label': `${label}: ${iso || t('wd.dateNotSet')}`,
        'aria-haspopup': 'dialog',
        'aria-expanded': open ? 'true' : 'false',
        onClick: () => { setView(iso ? new Date(`${iso}T12:00:00`) : new Date()); setOpen(o => !o) },
        children: face
      }, 'face'),
      jsx('input', {
        className: 'pa-dateinput',
        type: 'date',
        value: iso || '',
        tabIndex: -1,
        'aria-label': label,
        onChange: e => onChange(e.target.value)
      }, 'input'),
      iso
        ? jsx(Button, {
            className: 'pa-clear', variant: 'ghost', size: 'icon-xs',
            'aria-label': t('wd.dateClear'), ...hoverTip(t('wd.dateClear')),
            onClick: () => onChange(''), children: '×'
          }, 'clear')
        : null,
      open
        ? jsxs('div', {
            className: 'pa-cal',
            role: 'dialog',
            'aria-label': label,
            children: [
              jsxs('div', {
                className: 'pa-cal-head',
                children: [
                  jsx(Button, {
                    className: 'pa-icon', variant: 'ghost', size: 'icon-xs',
                    'aria-label': t('wd.calPrev'),
                    onClick: () => setView(new Date(year, month - 1, 1)), children: '‹'
                  }, 'prev'),
                  jsx('span', {
                    style: { ...mono, fontSize: TYPE.caption, color: 'var(--ui-text-secondary)', flex: 1,
                    textAlign: 'center' },
                    children: `${year}-${pad2(month + 1)}`
                  }, 'month'),
                  jsx(Button, {
                    className: 'pa-icon', variant: 'ghost', size: 'icon-xs',
                    'aria-label': t('wd.calNext'),
                    onClick: () => setView(new Date(year, month + 1, 1)), children: '›'
                  }, 'next')
                ]
              }),
              jsx('div', {
                className: 'pa-cal-wd',
                children: t('wd.weekdays').split(' ').map(w => jsx('span', { children: w }, w))
              }),
              jsx('div', {
                className: 'pa-cal-grid',
                'aria-label': `${label} · ${year}-${pad2(month + 1)}`,
                onKeyDown: calArrow,
                children: cells
              })
            ]
          }, 'cal')
        : null
    ]
  })
}

const sectionCard = (key, children) => jsx('div', { className: 'pa-sec', children }, key)

function SectionTitle({ title, meta, right, control }) {
  return jsxs('div', {
    className: 'pa-sectitle',
    children: [
      control || jsx(PanelSectionLabel, { children: title }, 'title'),
      jsx('span', {
        className: 'pa-secmeta',
        style: ell,
        ...hoverTip(meta),
        children: meta
      }, 'meta'),
      right ? jsx('span', { className: 'pa-secright', children: right }, 'right') : null
    ]
  })
}

function DailyChart({ t, buckets }) {
  const max = Math.max(1, ...buckets.map(b => b.n))
  return jsx('div', {
    className: 'pa-chart',
    style: { height: H.chart, display: 'flex', alignItems: 'flex-end', gap: 0 },
    children: buckets.map((b, i) => {
      const height = b.n ? Math.round((b.n / max) * 22) + 6 : 2
      return jsxs('div', {
        className: 'pa-bar-col',
        'data-zero': b.n ? '0' : '1',
        ...hoverTip(`${b.iso} · ${t('wd.rows', b.n)}`),
        children: [
          jsx('span', {
            className: 'pa-bar-count',
            style: { fontSize: TYPE.caption, color: 'var(--ui-text-secondary)', ...mono },
            children: b.n ? String(b.n) : ''
          }, 'n'),
          jsx('span', {
            className: 'pa-bar',
            'data-zero': b.n ? '0' : '1',
            style: { width: b.n ? '100%' : 10, maxWidth: 26, height }
          }, 'bar'),
          jsx('span', {
            className: 'pa-bar-day',
            style: { fontSize: TYPE.micro, color: 'var(--ui-text-secondary)', ...mono },
            children: b.day
          }, 'd')
        ]
      }, b.iso)
    })
  })
}

function drawerSection(key, label, bodyNode) {
  return jsxs('div', {
    className: 'pa-drawer-sec',
    children: [
      jsx(PanelSectionLabel, { children: label }, 'l'),
      bodyNode
    ]
  }, key)
}

const FOCUSABLE = 'button:not([disabled]),[href],input,[tabindex]:not([tabindex="-1"])'

function runSynopsis(t, row, body = row.body) {
  if (row.body_source === 'error' && String(body || '').trim()) {
    return { title: t('wd.reportedError'), text: String(body).trim().split(/\r?\n/)[0] }
  }
  const finding = row.findings?.find(item => item.tone === 'bad') || row.findings?.[0]
  if (finding) return { title: t('wd.reportedFinding'), text: findingEnglish(finding, t) }
  return { title: t('wd.reportedError'), text: row.status === 'failed'
    ? t('wd.errorNotRecorded') : t('wd.noReportedError') }
}

function Drawer({ t, row, nameOf, onClose, closing, returnKey, inline = false, snapshot = [] }) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')
  const [entered, setEntered] = useState(false)
  const [body, setBody] = useState(row.body || '')
  const [loading, setLoading] = useState(false)
  const [bodyError, setBodyError] = useState('')
  const [folded, setFolded] = useState([])
  const [picked, setPicked] = useState('')
  const ref = useRef(null)
  const copyable = typeof navigator !== 'undefined' && Boolean(navigator.clipboard?.writeText)
  useEffect(() => {
    ref.current?.focus?.({ preventScroll: true })
    const wrap = ref.current?.closest?.('.pa-logwrap')
    return () => {
      const back = [...(wrap?.querySelectorAll('.pa-log') || [])]
        .find(el => el.getAttribute('data-key') === returnKey)
      back?.focus?.({ preventScroll: true })
    }
  }, [])
  const trap = e => {
    if (e.key !== 'Tab') return
    const list = [...(ref.current?.querySelectorAll(FOCUSABLE) || [])]
    if (!list.length) return
    const first = list[0]
    const last = list[list.length - 1]
    const here = document.activeElement
    if (e.shiftKey && (here === first || here === ref.current)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && here === last) {
      e.preventDefault()
      first.focus()
    }
  }
  useEffect(() => {
    let alive = true
    setBody(row.body || '')
    setBodyError('')
    setLoading(false)
    if (!row.id || !(Number(row.body_len) > String(row.body || '').length)) return undefined
    setLoading(true)
    healthApi.jobRun(row.id)
      .then(res => {
        if (!alive) return
        if (res?.ok && res.id === row.id && typeof res.body === 'string') setBody(res.body)
        else setBodyError(String(res?.error || t('wd.noBodyAnswer')))
      })
      .catch(error => { if (alive) setBodyError(errText(error)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [row.id, row.body, row.body_len])
  useEffect(() => {
    const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : (fn => setTimeout(fn, 16))
    const handle = raf(() => setEntered(true))
    return () => {
      if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(handle)
      else clearTimeout(handle)
    }
  }, [])
  const copy = async () => {
    setCopyError('')
    try {
      await navigator.clipboard.writeText(body || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch (error) {
      setCopied(false)
      setCopyError(errText(error))
    }
  }
  const fold = key => setFolded(list => (list.includes(key)
    ? list.filter(k => k !== key)
    : list.concat(key)))
  const label = nameOf(row.job_id)
  const statusLabel = row.status === 'completed' ? t('wd.completed')
    : t(STATUS_BADGE[row.status] || 'wd.badge.unknown')
  const synopsis = runSynopsis(t, row, body)
  const durationRows = snapshot.filter(item => typeof item.duration_ms === 'number'
    && Number.isFinite(item.duration_ms) && item.duration_ms >= 0
    && typeof item.at_ts === 'number' && Number.isFinite(item.at_ts) && timeOf(item.at))
  const maxDuration = durationRows.reduce((max, item) => Math.max(max, item.duration_ms), 0)
  const summaryRows = [
    { label: t('wd.claimedAt'), value: timeOf(row.at) || t('wd.undated') },
    { label: t('wd.duration'), value: durationText(row.duration_ms, t) },
    { label: t('wd.notification'), value: t(DELIVERY_BADGE[row.delivery] || 'wd.badge.none') }
  ]
  const metaRows = [
    { label: t('wd.when'), value: row.at || t('wd.undated') },
    { label: t('wd.job'), value: label },
    { label: t('wa.jobId'), value: row.job_id || '—' },
    { label: t('wd.status'), value: row.status_label || row.status || '—' },
    { label: t('wd.delivery'), value: row.delivery_label || row.delivery || '—' },
    { label: t('wd.duration'), value: durationText(row.duration_ms, t) },
    { label: t('wd.lateness'), value: latenessText(row.lateness_s, t) },
    { label: t('wd.bodysrc'), value: row.body_label || t('wd.noBody') }
  ]
  return jsxs('div', {
    className: 'pa-drawer ch-inspector',
    role: inline ? 'region' : 'dialog',
    'aria-modal': inline ? undefined : 'true',
    'aria-label': label,
    id: inline ? 'chronicle-run-detail' : undefined,
    tabIndex: -1,
    onKeyDown: inline ? undefined : trap,
    ref,
    'data-in': entered && !closing ? '1' : '0',
    children: [
      jsxs('div', { className: 'pa-drawer-head ch-inspector-head', children: [
        jsxs('div', { className: 'ch-inspector-label', children: [
          jsx('i', { className: 'codicon codicon-file-text', 'aria-hidden': true }, 'icon'),
          jsx('span', { children: t('wd.runDetail') }, 'label')
        ] }, 'label'),
        jsx(Button, {
          className: 'pa-iconbtn', variant: 'ghost', size: 'icon-xs',
          'aria-label': t('wd.close'), ...hoverTip(t('wd.close')), onClick: onClose, children: '✕'
        }, 'close'),
        jsx('h2', { className: 'ch-inspector-title', children: label }, 'title'),
        jsxs('span', { className: 'ch-outcome', 'data-status': row.status, children: [
          jsx('i', { className: 'ch-outcome-dot', 'aria-hidden': true }, 'dot'),
          jsx('span', { children: statusLabel }, 'status')
        ] }, 'status')
      ] }, 'head'),
      jsxs(PanelDetail, { className: 'pa-drawer-body ch-inspector-body', children: [
        bodyError ? jsx('p', { className: 'pa-body-fail', role: 'status',
          children: t('wd.bodyFail', bodyError) }, 'fail') : null,
        copyError ? jsx('p', { className: 'pa-copy-fail', role: 'status',
          children: t('wd.copyFail', copyError) }, 'copyfail') : null,
        jsx(PanelMeta, { className: 'ch-summary', rows: summaryRows }, 'summary'),
        jsxs('section', { className: 'ch-error-section', 'aria-label': synopsis.title, children: [
          jsx('h3', { children: synopsis.title }, 'title'),
          jsx('p', { className: 'ch-error-preview', children: synopsis.text }, 'error')
        ] }, 'error'),
        jsxs('section', { className: 'ch-duration-section', 'aria-label': t('wd.durationSnapshot'), children: [
          jsx('h3', { children: t('wd.durationSnapshot') }, 'title'),
          jsx('p', { children: t('wd.durationSnapshotHint') }, 'hint'),
          durationRows.length ? jsx('div', { className: 'ch-duration-list', children: durationRows.map(item => {
            const clock = timeOf(item.at).slice(0, 5)
            const duration = durationText(item.duration_ms, t)
            return jsxs('div', {
              className: 'ch-duration-row', 'data-status': item.status, 'data-key': item.key,
              'data-selected': item.key === row.key ? '1' : '0',
              'aria-label': `${item.at} · ${nameOf(item.job_id)} · ${duration}`,
              ...hoverTip(`${item.at} · ${nameOf(item.job_id)} · ${duration}`),
              children: [
                jsx('time', { dateTime: item.at, children: clock }, 'time'),
                jsx('span', { className: 'ch-duration-track', 'aria-hidden': true,
                  children: jsx('i', { style: {
                    width: `${maxDuration > 0 ? item.duration_ms / maxDuration * 100 : 0}%`
                  } }, 'bar') }, 'track'),
                jsx('span', { className: 'ch-duration-value', children: duration }, 'value')
              ]
            }, item.key)
          }) }, 'bars') : jsx('p', { children: t('wd.durationNone') }, 'empty')
        ] }, 'durations'),
        jsx('p', { className: 'ch-trace-note', children: t('wd.traceNote') }, 'note'),
        jsxs('details', { className: 'ch-technical', children: [
          jsx('summary', { children: t('wd.technicalDetails') }, 'toggle'),
          jsxs('div', { className: 'ch-technical-body', children: [
            drawerSection('body',
              `${t('wd.field.body')}${loading ? ` · ${t('wd.loading')}` : ''}`,
              jsxs('div', { children: [
                jsx(PanelBlock, { className: 'pa-raw', children: body || t('wd.noBody') }, 'body'),
                copyable ? jsx(Button, {
                  className: 'pa-copy', variant: 'text', size: 'micro', onClick: () => void copy(),
                  children: copied ? t('wd.copied') : t('wd.copy')
                }, 'copy') : null,
              ] }, 'output')),
            row.findings?.length ? drawerSection('findings', t('wd.field.findings'),
              jsx(PanelList, { className: 'pa-findlist min-[47.5rem]:w-full',
                children: row.findings.map((f, i) => {
                  const raw = findingRaw(f)
                  const quote = raw ? `${t('wd.asWritten')}: ${raw}` : ''
                  const key = `${f.kind}-${i}`
                  const open = !folded.includes(key)
                  const active = picked ? picked === key : i === 0
                  return jsxs('div', {
                    className: 'pa-find', style: { display: 'flex', flexDirection: 'column', gap: 0 },
                    ...(quote ? hoverTip(quote) : {}), children: [
                      jsx(PanelListRow, {
                        active,
                        lead: badge('b', f.tone || '', {
                          style: { maxWidth: 200, flex: 'none' }, children: f.title
                        }),
                        onSelect: () => { setPicked(key); fold(key) }, rowKey: key,
                        title: jsx('p', { className: 'pa-drawer-txt', children: findingEnglish(f, t) }, 'mapped')
                      }, 'row'),
                      open ? jsxs('div', {
                        className: 'pa-findbody', style: { display: 'flex', flexDirection: 'column', gap: 4 },
                        children: [
                          jsx('p', { className: 'pa-drawer-txt', children: findingEnglish(f, t) }, 'mapped'),
                          quote ? jsx('p', { className: 'pa-quote', children: quote }, 'q') : null,
                          jsx('p', { className: 'pa-drawer-txt', children: f.what }, 'w'),
                          jsx('p', { className: 'pa-action', children: f.action }, 'a')
                        ]
                      }, 'body') : null
                    ]
                  }, key)
                })
              })) : null,
            row.job_live === false ? jsx('p', {
              className: 'pa-drawer-txt', children: t('wd.deletedNote')
            }, 'gone') : null,
            drawerSection('metadata', t('wd.runMetadata'),
              jsx(PanelMeta, { className: 'pa-kv', rows: metaRows }, 'kv'))
          ] }, 'body')
        ] }, 'technical')
      ] }, 'body')
    ]
  })
}

function RunRow({ t, row, open, onSelect, nameOf }) {
  const label = nameOf(row.job_id)
  const statusLabel = row.status === 'completed' ? t('wd.completed')
    : t(STATUS_BADGE[row.status] || 'wd.badge.unknown')
  const preview = runSynopsis(t, row).text
  const pointPath = row.status === 'completed' ? 'M3 7 6 10 11 4'
    : row.status === 'failed' ? 'M4 4 10 10 M4 10 10 4'
      : ACTIVE_STATUS.includes(row.status) ? 'M7 3v4l3 2' : 'M4 7h6'
  return jsxs('div', {
    className: 'pa-log ch-run', 'data-key': row.key, 'data-open': open ? '1' : '0',
    role: 'button', tabIndex: 0, 'aria-expanded': open, 'aria-controls': 'chronicle-run-detail',
    'aria-label': `${row.at || t('wd.undated')} · ${label} · `
      + `${row.status_label || row.status || t('wd.badge.unknown')}`,
    ...hoverTip(`${label} — ${row.status_label || row.status} · ${row.delivery_label || row.delivery}`),
    onClick: onSelect,
    onKeyDown: e => {
      if (e.key !== 'Enter' && e.key !== ' ') return
      e.preventDefault()
      onSelect()
    },
    children: [
      jsx('span', { className: 'ch-point', 'data-status': row.status, 'aria-hidden': true,
        children: jsx('svg', {
          width: 14, height: 14, viewBox: '0 0 14 14', fill: 'none', stroke: 'currentColor',
          strokeWidth: 1.3, strokeLinecap: 'round', strokeLinejoin: 'round', focusable: 'false',
          children: jsx('path', { d: pointPath }, 'path')
        }, 'icon')
      }, 'point'),
      jsxs('span', { className: 'ch-time', children: [
        jsx('time', { dateTime: row.at || undefined, children: timeOf(row.at).slice(0, 5) || '—' }, 'clock'),
        jsx('span', { children: row.date || t('wd.undated') }, 'date')
      ] }, 'time'),
      jsxs('span', { className: 'ch-description', children: [
        jsxs('span', { className: 'ch-jobline', children: [
          jsx('strong', { className: 'wa-clip', children: label }, 'job'),
          row.job_live === false ? jsx('span', {
            className: 'ch-history', children: t('wd.historicalJob')
          }, 'history') : null
        ] }, 'jobline'),
        jsx('span', { className: 'ch-preview', children: preview }, 'preview')
      ] }, 'description'),
      jsxs('span', { className: 'ch-facts', children: [
        jsxs('span', { className: 'ch-outcome', 'data-status': row.status, children: [
          jsx('i', { className: 'ch-outcome-dot', 'aria-hidden': true }, 'dot'),
          jsx('span', { children: statusLabel }, 'status')
        ] }, 'status'),
        jsx('span', { className: 'ch-run-duration', children: durationText(row.duration_ms, t) }, 'duration')
      ] }, 'facts'),
      jsx(Chevron, { size: 11, className: 'ch-caret',
        style: { transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
          transition: instantMove('caret', 'transform') } }, 'caret')
    ]
  }, row.key)
}

function LogGrid({ t, shown, openKey, setOpenKey, nameOf, review }) {
  const drawerRow = shown.find(row => row.key === openKey) || null
  return jsxs('div', { className: 'pa-logwrap ch-journal', 'data-drawer': drawerRow ? '1' : '0', children: [
    jsxs('div', { className: 'ch-journal-main', children: [
      jsx('div', { className: 'pa-logscroll ch-scroll', children: shown.map(row => jsx(RunRow, {
        t, row, nameOf, open: openKey === row.key,
        onSelect: () => setOpenKey(openKey === row.key ? '' : row.key)
      }, row.key)) }, 'list'),
      review || null
    ] }, 'main'),
    drawerRow ? jsx(Drawer, {
      t, row: drawerRow, nameOf, inline: true, closing: false, returnKey: drawerRow.key, snapshot: shown,
      onClose: () => setOpenKey('')
    }, drawerRow.key) : jsx('aside', {
      className: 'ch-inspector-empty', id: 'chronicle-run-detail', role: 'region',
      'aria-label': t('wd.runDetail'), children: jsx(PanelEmpty, {
        icon: 'file-text', title: t('wd.journalPick'), description: t('wd.journalPickHint')
      }, 'empty')
    }, 'pick')
  ] }, 'journal')
}

const colorItem = (tone, label) => jsxs('span', {
  className: 'pa-ck-item',
  children: [
    jsx('i', { className: 'pa-ck-dot', 'data-tone': tone }, 'dot'),
    jsx('span', { children: label }, 'label')
  ]
}, tone)

function ColorKey({ t }) {
  return jsxs('span', {
    className: 'pa-ck',
    children: [
      colorItem('bad', t('wd.ckBad')),
      colorItem('warn', t('wd.ckWarn')),
      colorItem('neutral', t('wd.ckNeutral'))
    ]
  })
}

function Legend({ t }) {
  return jsx('div', { className: 'pa-legend', children: jsx(ColorKey, { t }, 'ck') })
}

const TIP_W = 320
const TIP_EST_H = 54

function TipLayer({ tip }) {
  if (!tip?.text) return null
  const vw = typeof window === 'undefined' ? 1240 : (window.innerWidth || 1240)
  const vh = typeof window === 'undefined' ? 800 : (window.innerHeight || 800)
  const left = Math.min(Math.max(tip.x, 8), Math.max(8, vw - TIP_W - 8))
  const below = tip.y + 12
  const flip = below + TIP_EST_H > vh
  const top = Math.max(8, flip ? tip.y - (tip.h || 0) - TIP_EST_H : below)
  return jsx('div', {
    className: 'pa-tip',
    role: 'tooltip',
    'data-side': flip ? 'above' : 'below',
    style: { left, top },
    children: tip.text
  }, 'tip')
}

function emptyTitle(t, filters) {
  return filters.start || filters.end ? t('wd.emptyRangeTitle') : t('wd.emptyMatchTitle')
}

function emptyBody(t, filters) {
  if (filters.start || filters.end) return t('wd.emptyRangeBody')
  return filters.q.trim() ? t('wd.emptyMatchBody', filters.q.trim()) : t('wd.emptyPickBody')
}

function JobRunsPage({ data, error, refresh, busy, winRef }) {
  const t = usePluginI18n(PLUGIN_ID)
  const [filters, setFiltersState] = useState({ q: '', jobs: [], preset: 'all', start: '', end: '', status: 'all' })
  const [sort, setSort] = useState('new')
  const [openKey, setOpenKeyState] = useState('')
  const [tip, setTip] = useState(null)
  const [clearArmed, setClearArmed] = useState(false)
  const [clearBusy, setClearBusy] = useState(false)
  const [clearNote, setClearNote] = useState('')
  const archiveFlight = useRef(false)
  const clearScope = useRef(null)
  const setOpenKey = key => { setClearArmed(false); setClearNote(''); setOpenKeyState(key) }
  const setFilters = next => {
    setOpenKeyState(''); setClearArmed(false); setClearNote(''); setTip(null); setFiltersState(next)
  }
  const changeSort = next => { setOpenKeyState(''); setClearArmed(false); setSort(next) }
  const archiveClear = async (keys) => {
    const scope = clearScope.current
    if (archiveFlight.current || !scope?.ready || !keys?.length
      || !scope.armed || scope.armed.sig !== scope.sig || keys.some(key => !scope.keys.includes(key))) return
    archiveFlight.current = true
    setClearBusy(true)
    setClearNote('')
    try {
      const out = await healthApi.archiveClear(keys)
      if (!out || out.ok !== true) {
        setClearNote(t('wd.clearFail', (out && out.error) || t('wd.clearNoAnswer')))
      } else if (!out.cleared) {
        setClearNote(t('wd.clearNone'))
      } else {
        setClearNote(t('wd.cleared', out.cleared, out.missing || 0, out.archive || 'backups/'))
      }
    } catch (error) {
      setClearNote(t('wd.clearFail', errText(error)))
    } finally {
      archiveFlight.current = false
      setClearBusy(false)
      setClearArmed(false)
      setOpenKeyState('')
      refresh()
    }
  }

  useEffect(() => {
    TIP.set = setTip
    return () => { TIP.set = null }
  }, [])

  useEffect(() => {
    const win = WINDOW_FOR_PRESET[filters.preset]
    if (win && win !== winRef.current) {
      winRef.current = win
      refresh()
    }
  }, [filters.preset])

  useEffect(() => {
    if (!openKey) return undefined
    const onKey = e => {
      if (e.key !== 'Escape') return
      if (e.target?.closest?.('.pa-date')) return
      if (OPEN_POPS.size) return
      setOpenKey('')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [openKey])

  const registry = data?.registry || []
  const nameOf = jid => jobLabel(registry.find(e => e.id === jid) || { id: jid }, t)

  const all = (data?.runs || []).map(r => ({ ...r, key: String(r.id || `${r.job_id}@${r.at}`) }))

  const needle = filters.q.trim().toLocaleLowerCase()
  const scopeRows = all.filter(r => {
    if (needle) {
      const hay = [nameOf(r.job_id), r.status_label, r.delivery_label, r.body].join(' ').toLocaleLowerCase()
      if (!hay.includes(needle)) return false
    }
    if (filters.jobs.length && !filters.jobs.includes(r.job_id)) return false
    if (filters.start || filters.end) {
      if (!r.date) return false
      if (filters.start && r.date < filters.start) return false
      if (filters.end && r.date > filters.end) return false
    }
    return true
  })

  const status = filters.status || 'all'
  const shown = scopeRows.filter(row => status === 'all' || (status === 'active'
    ? ACTIVE_STATUS.includes(row.status) : row.status === status))
  const present = [...new Set(all.map(r => r.job_id))]
  const trend = data?.trend || null
  const sorted = shown.slice()
  if (sort === 'old') sorted.reverse()
  else if (sort === 'job') sorted.sort((a, b) => nameOf(a.job_id).localeCompare(nameOf(b.job_id)))
  else if (sort === 'status') {
    const rank = { failed: 0, claimed: 1, running: 1, completed: 2, unknown: 3 }
    sorted.sort((a, b) => (rank[a.status] ?? 4) - (rank[b.status] ?? 4))
  }
  const days = flowDays(shown, Math.floor(Date.now() / 1000))
  const buckets = dailyBuckets(shown, Math.floor(Date.now() / 1000), days)
  const maxDay = Math.max(1, ...buckets.map(b => b.n))
  const flowTotal = buckets.reduce((sum, b) => sum + b.n, 0)
  const peakIso = flowTotal ? buckets.find(b => b.n === maxDay)?.iso || '' : ''
  const flowPeak = peakIso ? `${peakIso.slice(8, 10)}.${peakIso.slice(5, 7)}` : ''
  const filtering = Boolean(filters.q || filters.jobs.length || filters.start || filters.end || status !== 'all')
  const clearable = shown.filter(r => r.id && !ACTIVE_STATUS.includes(r.status)).map(r => r.id)
  const clearSig = JSON.stringify(shown.map(row => [row.id, row.status]))
  clearScope.current = { keys: clearable, sig: clearSig, armed: clearArmed, ready: Boolean(data && !error && !busy) }
  useLayoutEffect(() => {
    if (openKey && !shown.some(row => row.key === openKey)) setOpenKeyState('')
    if (clearArmed && (clearArmed.sig !== clearSig || error)) setClearArmed(false)
  }, [clearSig, error, openKey, clearArmed])

  const shell = children => jsxs('div', {
    className: 'pa-root pa-health pa-chronicle',
    style: {
      height: '100%', minHeight: 0, overflow: 'auto',
      background: 'transparent', color: 'var(--ui-text-primary)'
    },
    children: [
      jsx('style', { children: WD_STYLE }),
      jsx(TopBar, { t, onRefresh: () => refresh(), busy }),
      stampLine({ t, data }),
      error && data
        ? jsx('div', {
            className: 'pa-stale',
            role: 'status',
            style: { padding: '4px 12px 0', fontSize: TYPE.caption, color: 'var(--ui-orange)' },
            children: t('wd.staleNotice', error?.message || String(error))
          }, 'stale')
        : null,
      ...children,
      jsx(TipLayer, { tip }, 'tip')
    ]
  })

  if (error && !data) {
    return shell([jsx('div', {
      className: 'pa-error',
      style: { padding: 14 },
      children: jsx(ErrorState, {
        title: t('wd.readErrorTitle'),
        description: `${t('wd.readError')}: ${error?.message || String(error)}`
      })
    }, 'error')])
  }

  if (!data) {
    return shell([jsx(Loader, { className: 'pa-loader', label: t('wd.loadingRuns') }, 'loading')])
  }

  if (!all.length) {
    return shell([jsx(PanelEmpty, {
      icon: 'watch',
      title: t('wd.emptyTitle'),
      description: t('wd.emptyBody')
    }, 'empty')])
  }

  const diagnostics = [
    sectionCard('freshness', [
      jsx(SectionTitle, {
        title: t('wd.frTitle'),
        meta: t('wd.frMeta', liveInScope(data, present).length)
      }, 't'),
      jsx(Freshness, {
        t,
        data,
        shown,
        present,
        nameOf,
        picked: filters.jobs,
        onPick: jid => setFilters(f => ({
          ...f,
          jobs: (f.jobs.length === 1 && f.jobs[0] === jid) ? [] : [jid]
        }))
      }, 'c')
    ]),
    jsx(KpiRow, { t, shown, trend }),
    sectionCard('chart', [
      jsx(SectionTitle, {
        title: t('wd.chartFlow'),
        meta: t('wd.chartFlowMeta', days),
        right: jsx('span', { className: 'pa-flowsum', children: t('wd.chartFlowSum', flowTotal, shown.length,
          flowPeak) }, 's')
      }, 't'),
      jsx(DailyChart, { t, buckets }, 'c')
    ]),
    sectionCard('activity', [
      jsx(SectionTitle, {
        title: t('wd.actTitle'),
        meta: t('wd.actMeta', (trend?.bucket_hours || 0) * (trend?.buckets || []).length, shown.length !== all.length)
      }, 't'),
      jsxs('div', {
        children: [
          jsx(ActivityCard, { t, trend, present, nameOf }, 'card')
        ]
      }, 'c')
    ]),
  ]
  const statusControl = jsxs('div', { className: 'ch-status', role: 'group', 'aria-label': t('wd.statusFilter'), children: [
    jsx(PanelSectionLabel, { children: t('wd.journalTitle') }, 'title'), jsx(SegmentedControl, {
      className: 'pa-seg', 'aria-label': t('wd.statusFilter'), value: status,
      onChange: next => setFilters(previous => ({ ...previous, status: next })),
      options: [['all', 'wd.all'], ['completed', 'wd.completed'], ['failed', 'wd.badge.failed'], ['active', 'wd.active']]
        .map(([id, key]) => ({ id, label: `${t(key)} ${scopeRows.filter(row => id === 'all'
          || (id === 'active' ? ACTIVE_STATUS.includes(row.status) : row.status === id)).length}` }))
    }, 'filter')] }, 'statuses')
  const journal = [
    sectionCard('logs', [
      jsx(SectionTitle, {
        title: t('wd.journalTitle'),
        control: statusControl,
        meta: filtering ? t('wd.filterHits', shown.length, all.length) : '',
        right: jsxs('span', {
          className: 'pa-logbars',
          style: { display: 'flex', alignItems: 'center', gap: 8 },
          children: [
            jsx(Button, {
              className: 'pa-clear-open',
              size: 'sm',
              variant: 'outline',
              'aria-expanded': clearArmed ? 'true' : 'false',
              'aria-label': t('wd.clearLabel'),
              disabled: Boolean(clearArmed) || clearBusy || busy || Boolean(error)
                || !clearable.length,
              onClick: () => {
                setClearNote(''); setOpenKeyState('')
                setClearArmed({ keys: clearable.slice(), sig: clearSig })
              },
              children: t('wd.clear')
            }, 'open'),
            jsx(Select, {
              id: 'sort',
              labelText: t('wd.sortSelect'),
              valueText: t(SORT_LABEL[sort]),
              options: SORT_IDS.map(id => ({ id, text: t(SORT_LABEL[id]) })),
              selectedId: sort,
              onPick: changeSort,
              align: 'right'
            }, 'sort')
          ]
        }, 'right')
      }, 't'),
      clearArmed && clearArmed.sig === clearSig
        ? jsxs('div', {
          className: 'pa-clear-ask',
          role: 'alertdialog',
          'aria-label': t('wd.clearLabel'),
          children: [
            jsx('p', { children: t('wd.clearAsk', shown.length, clearable.length, shown.length - clearable.length) }, 'q'),
            jsx(Button, {
              size: 'sm',
              variant: 'destructive',
              disabled: clearBusy || busy || Boolean(error) || !clearable.length,
              onClick: () => archiveClear(clearArmed.keys),
              children: clearBusy ? t('wd.clearBusy') : t('wd.clearGo')
            }, 'go'),
            jsx(Button, {
              size: 'sm',
              variant: 'outline',
              disabled: clearBusy,
              onClick: () => setClearArmed(false),
              children: t('wd.clearCancel')
            }, 'no')
          ]
        }, 'ask')
        : null,
      clearNote
        ? jsx('div', {
          className: 'pa-clear-note',
          children: clearNote
        }, 'note')
        : null,
      shown.length
        ? jsx(LogGrid, { t, shown: sorted, openKey, setOpenKey, nameOf }, 'c')
        : jsx(PanelEmpty, {
            icon: 'search',
            title: emptyTitle(t, filters),
            description: emptyBody(t, filters)
          }, 'c')
    ])
  ]
  return shell([jsx(FilterBar, { t, all, filters, setFilters, present, nameOf }, 'filters'), ...diagnostics, ...journal,
    jsx(Legend, { t }, 'legend')])
}





export default {
  id: PLUGIN_ID,
  name: 'Wiki Automation',
  register(ctx) {
    ctxRef = ctx
    ctx.i18n?.register?.(BUNDLES)
    const title = registerTitle()
    ctx.register({
      id: 'wa-page',
      area: AREA_ROUTES,
      data: { path: ROUTE },
      render: () => jsx(Page, {})
    })
    ctx.register({
      id: 'wa-nav',
      area: AREA_SIDEBAR_NAV,
      data: { path: ROUTE, label: title, codicon: 'settings-gear' }
    })
  }
}
