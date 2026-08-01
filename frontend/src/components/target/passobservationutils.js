const toTimestamp = (value) => {
    const timestamp = new Date(value).getTime();
    return Number.isFinite(timestamp) ? timestamp : null;
};

/**
 * Returns whether an enabled scheduled observation will cover this satellite pass.
 * Pass windows are compared rather than IDs because fresh pass calculations may
 * produce a different client-side ID for the same physical pass.
 */
export const isPassScheduledForAutomaticObservation = (pass, observations, satelliteId) => {
    const passStart = toTimestamp(pass?.event_start);
    const passEnd = toTimestamp(pass?.event_end);
    const passNoradId = String(satelliteId ?? pass?.norad_id ?? '').trim();

    if (passStart === null || passEnd === null || passEnd <= passStart || !passNoradId) {
        return false;
    }

    return (Array.isArray(observations) ? observations : []).some((observation) => {
        if (
            observation?.enabled === false
            || !['scheduled', 'running'].includes(observation?.status)
            || String(observation?.satellite?.norad_id ?? '').trim() !== passNoradId
        ) {
            return false;
        }

        const observationStart = toTimestamp(observation?.pass?.event_start);
        const observationEnd = toTimestamp(observation?.pass?.event_end);
        if (observationStart === null || observationEnd === null || observationEnd <= observationStart) {
            return false;
        }

        return passStart < observationEnd && passEnd > observationStart;
    });
};
