## MODIFIED Requirements

### Requirement: Symbol-loop collectors must support resume progress

Symbol-loop collection jobs SHALL persist symbol-level progress when their work can be safely split by symbol.

#### Scenario: Starting a symbol-loop job
- **WHEN** a resumable symbol-loop job starts
- **THEN** it SHALL initialize `remaining_symbols` from the requested symbol set
- **AND** it SHALL process only `remaining_symbols`

#### Scenario: A symbol-loop job completes one symbol
- **WHEN** one symbol finishes successfully
- **THEN** collector SHALL remove that symbol from `remaining_symbols`

#### Scenario: A symbol-loop job fails one symbol
- **WHEN** one symbol fails
- **THEN** collector SHALL keep that symbol in `remaining_symbols`
- **AND** it SHALL add that symbol to `failed_symbols`
- **AND** it MAY continue processing later symbols before failing the job

#### Scenario: All remaining symbols have already completed
- **WHEN** a retried symbol-loop job has no remaining symbols
- **THEN** collector SHALL skip service execution and clear resume fields
