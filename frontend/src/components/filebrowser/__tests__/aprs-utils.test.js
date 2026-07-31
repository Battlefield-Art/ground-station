import {describe, expect, it} from 'vitest';
import {getAprsData, getAprsDataTypeLabel} from '../aprs-utils.js';

describe('APRS file metadata normalization', () => {
    it('uses structured APRS metadata from newly decoded packets', () => {
        const structured = {
            format: 'aprs',
            data_type_identifier: '!',
            position: {latitude: 40.6, longitude: 22.96},
        };
        const metadata = {telemetry: {telemetry: structured}};

        expect(getAprsData(metadata)).toBe(structured);
        expect(getAprsDataTypeLabel(structured)).toBe('Position without timestamp');
    });

    it('recovers position and Base91 telemetry from older APRS metadata', () => {
        const metadata = {
            telemetry: {
                telemetry: {
                    format: 'raw',
                    ascii: '!L9y@)T<7Ca  GLoRa APRS|&:%X|',
                },
            },
        };

        const aprs = getAprsData(metadata);
        expect(aprs.position).toEqual({
            latitude: 40.601269,
            longitude: 22.967211,
            format: 'compressed',
            symbol_table: 'L',
            symbol_code: 'a',
        });
        expect(aprs.comment).toBe('GLoRa APRS');
        expect(aprs.telemetry).toEqual({
            encoding: 'base91',
            sequence: 480,
            channels: [419],
            raw: '&:%X',
        });
    });
});
