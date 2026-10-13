# Agent scenario test pool — single source of truth (dot-source from run_agent_test_pool.ps1).
# Does not replace ci_mandatory_checks or targeted pytest after each task.

function Get-AgentTestPoolProfileTable {
    @{
        local = @{
            Label   = "Local file-job, engine chunks, progress"
            PyTests = @(
                "tests/test_api_files.py"
                "tests/test_engine_server.py"
                "tests/test_transcribe_streaming.py"
                "tests/test_job_resume.py"
                "tests/test_chunking.py"
            )
            Smokes  = @("scripts/smoke_engine_cancel_sequence.py")
        }
        cloud = @{
            Label   = "Cloud-only and remote streaming"
            PyTests = @(
                "tests/test_cloud_only.py::test_cloud_only_start_local_job_fails"
                "tests/test_cloud_only.py::test_cloud_only_without_key_does_not_call_remote"
                "tests/test_remote_streaming.py"
            )
            Smokes  = @("scripts/smoke_cloud_batch_route.py")
        }
        youtube = @{
            Label   = "YouTube ingest and API (mock, no live network in Core)"
            PyTests = @(
                "tests/test_youtube_api.py"
                "tests/test_youtube_ingest.py"
                "tests/test_youtube_batch_api.py"
            )
            Smokes  = @(
                @{
                    Path = "scripts/smoke_youtube_ingest.py"
                    Env  = @{ SLYSH_SMOKE_YOUTUBE_LIVE = "0" }
                }
            )
        }
        resume = @{
            Label   = "Start, stop, export, resume, retranscribe"
            PyTests = @(
                "tests/test_partial_transcribe_e2e.py"
                "tests/test_job_asr_snapshot.py"
            )
            Smokes  = @()
        }
        export = @{
            Label   = "Export formats and path collisions"
            PyTests = @(
                "tests/test_export.py"
                "tests/test_batch_export.py"
            )
            Smokes  = @("scripts/smoke_batch_export_collision.py")
        }
        batch = @{
            Label   = "Batch queue and packages"
            PyTests = @(
                "tests/test_batch_api.py"
                "tests/test_batch_runner.py"
            )
            Smokes  = @("scripts/smoke_batch_on_error_stop.py")
        }
        capture = @{
            Label   = "Live and meeting: stop, finalize, pause"
            PyTests = @(
                "tests/test_live_stop_async_finalize.py"
                "tests/test_capture_finalize_coordinator.py"
            )
            Smokes  = @(
                "scripts/smoke_capture_pause_resume.py"
                "scripts/smoke_capture_job_finalizing_status.py"
            )
        }
        library = @{
            Label   = "Library duration, has_transcript, no ffprobe on list"
            PyTests = @(
                "tests/test_job_media_duration.py"
                "tests/test_library_check_existing.py"
            )
            Smokes  = @()
        }
        progress = @{
            Label   = "Streaming progress and finalize 1.0"
            PyTests = @(
                "tests/test_job_resume.py"
                "tests/test_transcribe_streaming.py"
                "tests/test_api_files.py"
            )
            Smokes  = @()
        }
        ui = @{
            Label   = "UI process: no torch import, legacy exports"
            PyTests = @("tests/test_ui_imports.py")
            Smokes  = @("scripts/smoke_web_legacy_exports.py")
        }
    }
}

function Get-AgentTestPoolTierTable {
    @{
        Core = @{
            Label    = "Scenarios without network or real engine (default)"
            Profiles = @(
                "local", "cloud", "youtube", "resume", "export", "library", "progress", "ui"
            )
        }
        Extended = @{
            Label    = "Core plus batch, capture, extended batch export"
            Profiles = @(
                "local", "cloud", "youtube", "resume", "export", "library", "progress", "ui"
                "batch", "capture"
            )
            ExtraPyTests = @(
                "tests/test_meeting_capture.py"
                "tests/test_live_buffer.py"
            )
            ExtraSmokes  = @("scripts/smoke_batch_export_runner_e2e.py")
        }
        Live = @{
            Label  = "Real engine and YouTube live (opt-in, may SKIP)"
            Smokes = @(
                @{
                    Path = "scripts/smoke_transcribe_user_jobs.py"
                    WarnOnMissingVenv = $true
                }
                @{
                    Path = "scripts/smoke_youtube_ingest.py"
                    Env  = @{ SLYSH_SMOKE_YOUTUBE_LIVE = "1" }
                }
            )
        }
    }
}

function Resolve-AgentTestPoolItems {
    param(
        [ValidateSet("Core", "Extended", "Live", "All")]
        [string] $Tier = "Core",
        [string[]] $ScenarioProfile = @()
    )

    $profiles = Get-AgentTestPoolProfileTable
    $tiers = Get-AgentTestPoolTierTable

    $profileNames = @()
    if ($ScenarioProfile.Count -gt 0) {
        foreach ($item in $ScenarioProfile) {
            foreach ($part in ($item -split ",")) {
                $name = $part.Trim()
                if ($name) {
                    $profileNames += $name
                }
            }
        }
    } elseif ($Tier -eq "Live") {
        $profileNames = @()
    } elseif ($Tier -eq "All") {
        $profileNames = $tiers.Extended.Profiles
    } else {
        $profileNames = $tiers[$Tier].Profiles
    }

    $pyTests = [System.Collections.Generic.HashSet[string]]::new()
    $smokes = [System.Collections.ArrayList]::new()

    foreach ($name in $profileNames) {
        if (-not $profiles.ContainsKey($name)) {
            throw "Unknown profile: $name"
        }
        $entry = $profiles[$name]
        foreach ($p in $entry.PyTests) { [void]$pyTests.Add($p) }
        foreach ($s in $entry.Smokes) { [void]$smokes.Add($s) }
    }

    if ($Tier -eq "Extended" -or $Tier -eq "All") {
        foreach ($p in $tiers.Extended.ExtraPyTests) { [void]$pyTests.Add($p) }
        foreach ($s in $tiers.Extended.ExtraSmokes) { [void]$smokes.Add($s) }
    }

    $liveSmokes = @()
    if ($Tier -eq "Live" -or $Tier -eq "All") {
        foreach ($s in $tiers.Live.Smokes) { [void]$smokes.Add($s) }
        $liveSmokes = $tiers.Live.Smokes
    }

    return @{
        PyTests    = @($pyTests | Sort-Object)
        Smokes     = @($smokes)
        ProfileNames = $profileNames
        Tier       = $Tier
        LiveSmokes = $liveSmokes
    }
}
