import { describe, expect, it } from 'vitest';

import {
    DECODER_SUPPORT,
    getDecoderDefaultParameters,
    getDecoderParameters,
    mapParametersToBackend,
} from '../decoder-parameters.js';

describe('APRS decoder parameters', () => {
    it('offers APRS and keeps the legacy AFSK decoder disabled', () => {
        expect(DECODER_SUPPORT.aprs).toBe(true);
        expect(DECODER_SUPPORT.afsk).toBe(false);
        expect(Object.keys(getDecoderParameters('afsk'))).toHaveLength(0);
    });

    it('uses Bell 202 defaults and maps them to the raw-IQ backend decoder', () => {
        const defaults = getDecoderDefaultParameters('aprs');

        expect(defaults).toEqual({
            aprs_baudrate: 1200,
            aprs_af_carrier: 1700,
            aprs_deviation: 500,
        });
        expect(mapParametersToBackend('aprs', defaults)).toEqual({
            baudrate: 1200,
            af_carrier: 1700,
            deviation: 500,
            framing: 'aprs',
        });
    });
});
