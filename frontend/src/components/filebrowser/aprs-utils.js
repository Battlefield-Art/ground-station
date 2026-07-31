const APRS_DATA_TYPES = {
    '!': 'Position without timestamp',
    '=': 'Position with messaging',
    '/': 'Position with timestamp',
    '@': 'Position with timestamp and messaging',
    ';': 'Object',
    ')': 'Item',
    ':': 'Message',
    '>': 'Status',
    T: 'Telemetry',
    _: 'Weather',
    '`': 'Mic-E',
    "'": 'Mic-E (old)',
};

function decodeBase91(value) {
    return [...value].reduce((decoded, character) => (decoded * 91) + character.charCodeAt(0) - 33, 0);
}

function textFromHex(hex) {
    if (!hex || hex.length % 2 !== 0) return '';
    try {
        return String.fromCharCode(...(hex.match(/.{2}/g) || []).map((byte) => Number.parseInt(byte, 16)));
    } catch {
        return '';
    }
}

function parseCoordinate(value, degreeDigits) {
    const hemisphere = value.at(-1);
    const normalized = value.slice(0, -1).replaceAll(' ', '5');
    const degrees = Number.parseInt(normalized.slice(0, degreeDigits), 10);
    const minutes = Number.parseFloat(normalized.slice(degreeDigits));
    if (!Number.isFinite(degrees) || !Number.isFinite(minutes)) return null;
    const sign = hemisphere === 'S' || hemisphere === 'W' ? -1 : 1;
    return Number((sign * (degrees + minutes / 60)).toFixed(6));
}

function parseLegacyPosition(payload) {
    if (!payload || !['!', '=', '/', '@'].includes(payload[0])) return null;
    const timestampLength = ['/', '@'].includes(payload[0]) ? 7 : 0;
    const body = payload.slice(1 + timestampLength);
    const uncompressed = body.match(/^(\d{2}[0-9 ]{2}\.[0-9 ]{2}[NS])(.)(\d{3}[0-9 ]{2}\.[0-9 ]{2}[EW])(.)/);
    if (uncompressed) {
        return {
            position: {
                latitude: parseCoordinate(uncompressed[1], 2),
                longitude: parseCoordinate(uncompressed[3], 3),
                format: 'uncompressed',
                symbol_table: uncompressed[2],
                symbol_code: uncompressed[4],
            },
            comment: body.slice(uncompressed[0].length),
        };
    }

    const base91Position = body.length >= 10
        && [...body.slice(1, 9)].every((character) => character.charCodeAt(0) >= 33 && character.charCodeAt(0) <= 123);
    if (!base91Position) return null;
    const latitude = 90 - decodeBase91(body.slice(1, 5)) / 380926;
    const longitude = -180 + decodeBase91(body.slice(5, 9)) / 190463;
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
    const hasCompressedExtension = body.length >= 13
        && [...body.slice(10, 13)].every((character) => character.charCodeAt(0) >= 33 && character.charCodeAt(0) <= 123);
    return {
        position: {
            latitude: Number(latitude.toFixed(6)),
            longitude: Number(longitude.toFixed(6)),
            format: 'compressed',
            symbol_table: body[0],
            symbol_code: body[9],
        },
        comment: body.slice(hasCompressedExtension ? 13 : 10),
    };
}

function parseLegacyAprs(payload) {
    if (!payload) return null;
    const identifier = payload[0];
    const parsed = {
        format: 'aprs',
        raw: payload,
        data_type_identifier: identifier,
        data_type: APRS_DATA_TYPES[identifier] || 'Unknown',
        values: {},
    };
    const positionData = parseLegacyPosition(payload);
    if (positionData) {
        parsed.position = positionData.position;
        parsed.values.latitude_degrees = positionData.position.latitude;
        parsed.values.longitude_degrees = positionData.position.longitude;
        let comment = positionData.comment;
        const telemetryMatch = comment.match(/\|([!-{]{4,14})\|/);
        if (telemetryMatch) {
            const pairs = telemetryMatch[1].match(/.{2}/g) || [];
            const values = pairs.map(decodeBase91);
            parsed.telemetry = {
                encoding: 'base91',
                sequence: values[0],
                channels: values.slice(1),
                raw: telemetryMatch[1],
            };
            comment = comment.replace(telemetryMatch[0], '');
        }
        parsed.comment = comment.trim();
    }
    return parsed;
}

export function getAprsData(metadata) {
    const telemetry = metadata?.telemetry || {};
    const structured = telemetry?.telemetry;
    if (structured?.format === 'aprs') return structured;

    // Files decoded before APRS parsing was introduced contain the information
    // field as generic ASCII/hex. Parse enough here to keep those files useful.
    const payload = structured?.ascii || textFromHex(telemetry?.raw?.payload_hex);
    return parseLegacyAprs(payload);
}

export function getAprsDataTypeLabel(aprs) {
    const identifier = aprs?.data_type_identifier;
    return APRS_DATA_TYPES[identifier]
        || String(aprs?.data_type || 'Unknown').replaceAll('_', ' ');
}
