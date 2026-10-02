import { expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({sid:'s',sd:{prep:{derivedRef:''},insight:{confirmed:['I1']}}}));
const view = vi.hoisted(() => ({version:'v2',readonly:false,conflict:false,session:null}));
vi.mock('@/stores/useSessionStore', () => ({useSessionStore:() => state}));
vi.mock('@/components/versions/VersionProvider', () => ({useVersion:() => view}));
vi.mock('@/components/persona/InsightScreen', () => ({InsightScreen:() => null}));
vi.mock('@/app/insights/LegacyInsightsPage', () => ({default:() => null}));
vi.mock('next/navigation', () => ({redirect:vi.fn()}));
import Page from '@/app/pipeline/insights/page';
import OldPage from '@/app/insights/page';
import { InsightScreen } from './InsightScreen';
import Legacy from '@/app/insights/LegacyInsightsPage';
import { redirect } from 'next/navigation';
it('redirects /insights to the pipeline route', () => {OldPage();expect(redirect).toHaveBeenCalledWith('/pipeline/insights');});
it('retains old insights component for legacy sessions', () => {state.sd.prep.derivedRef='';expect(Page().type).toBe(Legacy);});
it('passes session, selected version, confirmations and conflict readonly to new screen', () => {
 state.sd.prep.derivedRef='derived';view.conflict=true;
 const page = Page();expect(page.type).toBe(InsightScreen);expect(page.props).toMatchObject({sid:'s',version:'v2',readonly:true,initialConfirmed:['I1']});
});
