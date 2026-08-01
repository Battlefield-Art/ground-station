import { describe, expect, it } from 'vitest';
import { isPassScheduledForAutomaticObservation } from '../passobservationutils';

const pass = {
    norad_id: 25544,
    event_start: '2026-08-01T10:00:00Z',
    event_end: '2026-08-01T10:10:00Z',
};

const observationForPass = (overrides = {}) => ({
    enabled: true,
    status: 'scheduled',
    satellite: { norad_id: 25544 },
    pass: {
        event_start: '2026-08-01T10:00:00Z',
        event_end: '2026-08-01T10:10:00Z',
    },
    ...overrides,
});

describe('isPassScheduledForAutomaticObservation', () => {
    it('matches enabled scheduled observations for the same satellite and pass window', () => {
        expect(isPassScheduledForAutomaticObservation(
            pass,
            [observationForPass({ pass: { event_start: '2026-08-01T10:01:00Z', event_end: '2026-08-01T10:09:00Z' } })],
            25544,
        )).toBe(true);
    });

    it('does not mark disabled, terminal, or other-satellite observations', () => {
        expect(isPassScheduledForAutomaticObservation(pass, [
            observationForPass({ enabled: false }),
            observationForPass({ status: 'completed' }),
            observationForPass({ satellite: { norad_id: 99999 } }),
        ], 25544)).toBe(false);
    });

    it('marks a running observation while its pass is visible', () => {
        expect(isPassScheduledForAutomaticObservation(
            pass,
            [observationForPass({ status: 'running' })],
            25544,
        )).toBe(true);
    });
});
