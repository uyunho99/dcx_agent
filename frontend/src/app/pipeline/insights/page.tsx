'use client';
import { useSessionStore } from '@/stores/useSessionStore';
import { useVersion } from '@/components/versions/VersionProvider';
import { InsightScreen } from '@/components/persona/InsightScreen';
import LegacyInsightsPage from '@/app/insights/LegacyInsightsPage';
export default function InsightsPage() {
 const {sid,sd} = useSessionStore();
 const view = useVersion();
 const session = view.session ?? sd;
 const prep = session?.prep as {derivedRef?: unknown} | undefined;
 const insight = session?.insight as {confirmed?: string[]} | undefined;
 if (prep?.derivedRef && sid) return <InsightScreen key={`${sid}:${view.version ?? ''}`} sid={sid} version={view.version} readonly={view.readonly || !!view.conflict} initialConfirmed={insight?.confirmed ?? []}/>;
 return <LegacyInsightsPage/>;
}
