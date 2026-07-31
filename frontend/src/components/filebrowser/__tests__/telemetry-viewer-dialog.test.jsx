import React from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import TelemetryViewerDialog from '../telemetry-viewer-dialog.jsx';

vi.mock('../telemetry-aprs-tab.jsx', () => ({
    default: () => <div>Dedicated APRS packet view</div>,
}));
vi.mock('../telemetry-overview-tab', () => ({
    default: () => <div>Packet overview</div>,
}));

const file = {filename: 'packet.bin', url: '/decoded/packet.bin'};

describe('TelemetryViewerDialog packet-specific tab', () => {
    it('replaces Telemetry with APRS for APRS decoder files', () => {
        render(
            <TelemetryViewerDialog
                open
                onClose={() => {}}
                file={file}
                metadata={{decoder: {type: 'aprs'}, telemetry: {}, packet: {}}}
            />,
        );

        const aprsTab = screen.getByRole('tab', {name: 'APRS'});
        expect(screen.queryByRole('tab', {name: 'Telemetry'})).not.toBeInTheDocument();
        fireEvent.click(aprsTab);
        expect(screen.getByText('Dedicated APRS packet view')).toBeInTheDocument();
    });

    it('keeps the generic Telemetry tab for other decoder files', () => {
        render(
            <TelemetryViewerDialog
                open
                onClose={() => {}}
                file={file}
                metadata={{decoder: {type: 'fsk'}, telemetry: {}, packet: {}}}
            />,
        );

        expect(screen.getByRole('tab', {name: 'Telemetry'})).toBeInTheDocument();
        expect(screen.queryByRole('tab', {name: 'APRS'})).not.toBeInTheDocument();
    });
});
