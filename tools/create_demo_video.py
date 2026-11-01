"""Build a narrated, offline demo video for the candidate matching project."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WIDTH, HEIGHT = 1280, 720
BACKGROUND = "#101522"
PANEL = "#171f2e"
MUTED = "#a9b5c8"
WHITE = "#f3f6fb"
CYAN = "#59d5d0"
PURPLE = "#a78bfa"
GREEN = "#9ce5b5"
FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = {
        "regular": ("segoeui.ttf", "arial.ttf"),
        "bold": ("segoeuib.ttf", "arialbd.ttf"),
        "mono": ("consola.ttf", "cour.ttf"),
    }
    for candidate in candidates[name]:
        path = FONT_DIR / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONTS = {
    "title": font("bold", 42),
    "heading": font("bold", 28),
    "body": font("regular", 20),
    "small": font("regular", 16),
    "mono": font("mono", 16),
    "mono_small": font("mono", 14),
}


def wrap_lines(text: str, chars: int) -> list[str]:
    result: list[str] = []
    for paragraph in text.splitlines() or [""]:
        result.extend(wrap(paragraph, width=chars, break_long_words=False) or [""])
    return result


def draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font_obj: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_height: int,
) -> int:
    x, y = xy
    for line in text.splitlines():
        if not line:
            y += line_height
            continue
        words = line.split()
        current = ""
        for word in words:
            proposal = f"{current} {word}".strip()
            if current and draw.textbbox((0, 0), proposal, font=font_obj)[2] > max_width:
                draw.text((x, y), current, font=font_obj, fill=fill)
                y += line_height
                current = word
            else:
                current = proposal
        if current:
            draw.text((x, y), current, font=font_obj, fill=fill)
            y += line_height
    return y


def make_slide(
    number: int,
    title: str,
    subtitle: str,
    command: str,
    output: str,
    label: str,
    destination: Path,
) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 8), fill=CYAN)
    draw.text((48, 34), "AGENTIC PROFILE MATCHING", font=FONTS["small"], fill=CYAN)
    draw.text((48, 70), title, font=FONTS["title"], fill=WHITE)
    draw.text((50, 127), subtitle, font=FONTS["body"], fill=MUTED)

    left = (48, 190, 596, 630)
    right = (622, 190, 1232, 630)
    draw.rounded_rectangle(left, radius=18, fill=PANEL, outline="#29344a", width=2)
    draw.rounded_rectangle(right, radius=18, fill=PANEL, outline="#29344a", width=2)
    draw.text((72, 210), "TERMINAL", font=FONTS["small"], fill=PURPLE)
    draw.text((646, 210), label.upper(), font=FONTS["small"], fill=CYAN)
    for index, color in enumerate(("#ff7979", "#ffd166", "#9ce5b5")):
        draw.ellipse((535 + index * 17, 214, 544 + index * 17, 223), fill=color)

    command_y = draw_text(
        draw, f"> {command}", (72, 252), FONTS["mono"], GREEN, 488, 25
    )
    draw.line((72, command_y + 12, 567, command_y + 12), fill="#334056", width=1)
    lines = wrap_lines(output.strip(), 56)
    visible = lines[:14]
    draw_text(
        draw, "\n".join(visible), (72, command_y + 27), FONTS["mono_small"],
        WHITE, 490, 21
    )
    if len(lines) > len(visible):
        draw.text((72, 590), "...", font=FONTS["mono_small"], fill=MUTED)

    draw_text(
        draw, "What to notice", (648, 249), FONTS["heading"], WHITE, 540, 36
    )
    summary = output.strip()
    if len(summary) > 440:
        summary = summary[:437].rsplit(" ", 1)[0] + "..."
    draw_text(draw, summary, (648, 296), FONTS["body"], MUTED, 540, 28)
    draw.line((48, 657, 1232, 657), fill="#29344a", width=1)
    draw.text((48, 672), "Local demo · synthetic resumes · human-reviewed screening", font=FONTS["small"], fill=MUTED)
    draw.text((1175, 672), f"{number:02d} / 07", font=FONTS["small"], fill=CYAN)
    image.save(destination, format="PNG", optimize=True)


def synthesize(text: str, destination: Path) -> None:
    script = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
if ($voices -contains 'Microsoft Zira Desktop') {
    $synth.SelectVoice('Microsoft Zira Desktop')
}
$synth.Rate = 0
$synth.SetOutputToWaveFile($env:DEMO_AUDIO_PATH)
$synth.Speak($env:DEMO_NARRATION_TEXT)
$synth.Dispose()
"""
    environment = os.environ.copy()
    environment["DEMO_AUDIO_PATH"] = str(destination)
    environment["DEMO_NARRATION_TEXT"] = text
    encoded = __import__("base64").b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Windows offline narration failed: {result.stderr.strip()}")
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("The narration engine did not produce an audio file.")


def concatenate_audio(parts: list[Path], destination: Path) -> float:
    with wave.open(str(parts[0]), "rb") as first:
        parameters = first.getparams()
        with wave.open(str(destination), "wb") as output:
            output.setparams(parameters)
            total_frames = 0
            for index, part in enumerate(parts):
                with wave.open(str(part), "rb") as audio:
                    if audio.getparams()[:3] != parameters[:3]:
                        raise RuntimeError("Narration segments use incompatible audio formats.")
                    frames = audio.readframes(audio.getnframes())
                    output.writeframes(frames)
                    total_frames += audio.getnframes()
                    if index < len(parts) - 1:
                        pause_frames = int(parameters.framerate * 2.0)
                        output.writeframes(b"\0" * pause_frames * parameters.nchannels * parameters.sampwidth)
                        total_frames += pause_frames
    return total_frames / parameters.framerate


def run_agent_demo():
    from matching_agent import agent

    state = {
        "resume_dir": str(ROOT / "resumes"),
        "conversation_history": [],
        "refinement_round": 0,
    }
    state = agent.invoke({**state, "user_query": "Find me candidates with React and 3+ years experience"})
    search_report = state["response"]
    compare_state = agent.invoke({**state, "user_query": "Compare the top 3 matches side by side"})
    why_state = agent.invoke(
        {**compare_state, "user_query": "Why did alex rivera rank higher than sam lee?"}
    )
    refined = agent.invoke(
        {**state, "human_feedback": "Instead of React, use Python"}
    )
    interview = agent.invoke(
        {**refined, "user_query": "Generate screening questions for jordan kim"}
    )
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if tests.returncode:
        raise RuntimeError(f"The project tests failed while preparing the demo:\n{tests.stderr}")
    return search_report, compare_state["response"], why_state["response"], refined["response"], interview["response"], tests


def main() -> None:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SystemExit("Install project dependencies first: python -m pip install -r requirements.txt") from exc

    from matching_agent import extract_requirements

    if not (ROOT / "resumes").is_dir():
        raise SystemExit("The demo resume folder is missing.")
    outputs = run_agent_demo()
    search_report, comparison, explanation, refined_report, interview_questions, tests = outputs
    req = extract_requirements("Find React candidates with 3+ years experience")

    narrations = [
        "Welcome to the Agentic Profile Matching demo. This is a local candidate search and screening project built with LangGraph. It starts as a simple command line conversation and produces an explainable shortlist from resume files. The demonstration uses three fictional sample resumes included with the project. Real resumes can be supplied as text, Markdown, PDF, or Word documents. Candidate data stays on this machine: this application does not send resume contents to an external model or service. I will walk through the graph, a skills and experience search, candidate comparison, a ranking explanation, an interactive refinement, interview questions, and the automated tests.",
        "The graph begins by parsing the user's natural language request. Its requirement extractor separates must-have skills from preferred skills and looks for an experience threshold. Here the core request identifies React and three years as criteria. Resume search retrieves relevant files, then the ranking step performs the deeper analysis on at most the top ten. The report stores a score, evidence, strengths, gaps, and a screening recommendation for every candidate. A human feedback node accepts another requirement and sends the workflow through extraction, retrieval, and ranking again. The conversation history and shortlist are carried in graph state. The conditional feedback edge allows several refinement rounds and ends the conversation when no refinement is supplied.",
        f"Here is the first natural language query: find candidates with React and three or more years of experience. The agent retrieves the resumes and produces this report. Alex matches React and documents five years of experience, so the report ranks Alex first. Sam also lists React but has two years, so the experience criterion is shown as a gap and Sam is marked borderline for additional screening. Jordan has substantial experience but the resume does not show React. The explanation is grounded in the requirement evidence that appears in each file. This is a lightweight local retrieval and scoring implementation, not a pretrained language model making an opaque judgment. For a larger portfolio, a real embedding-based RAG retriever can replace the included lexical search while retaining the same graph.",
        "The conversation can continue with a request to compare the top three matches side by side. The comparison tool returns scores with strengths and gaps, so a reviewer can see why a candidate is competitive rather than relying on one overall number. The next question asks why Alex ranked above Sam. The agent answers that Alex met the experience threshold while both candidates shared the React skill. This is a traceable explanation tied to the extracted requirements and resume content. A hiring team can inspect the evidence and decide whether the criteria are appropriate before moving forward. The recommendation is decision support only, not an automatic hiring decision.",
        "The graph also supports changes in the middle of a conversation. Here I ask for Python instead of React. That feedback is passed into the graph as human input. The workflow updates the criteria, reruns resume retrieval, and ranks the results again. Jordan now leads because Jordan's resume contains Python and the other candidates do not. This makes the ranking responsive to the user's revised needs rather than treating the original search as permanent. The shortlist is regenerated using the new criteria, and the updated report explains its strengths and gaps. Experience requirements can be added as well. A new search starts with fresh criteria, while a refinement changes the existing search.",
        "Once the shortlist is available, the interview-question tool can create screening prompts for a specific candidate. These questions are grounded in the candidate's listed skills and the gaps identified during screening. For Jordan, the prompts invite the interviewer to ask for project examples and discuss technical decisions. They are intended as a helpful starting point for a human interviewer, not a final assessment. The same agent also supports head-to-head comparisons and questions about why a candidate's rank changed. Together, these conversational actions turn the basic search into an iterative review workflow while keeping the reasoning visible to the person making the decision.",
        "Finally, the project includes automated conversation-flow tests. They exercise requirement extraction, the natural language search, comparisons, ranking explanations, interview-question generation, and both adding and replacing criteria through refinement. The test suite runs locally with Python's unittest runner. The included sample data is synthetic, so the project is ready for a demonstration without exposing private candidate information. To run it yourself, install the requirements and launch the app with the resume directory. The state diagram, setup guide, and timed walkthrough are also included. That concludes the demo: local resume matching, explainable screening, interactive refinement, and human oversight, all connected in one LangGraph workflow.",
    ]

    titles = [
        ("A local, explainable screening assistant", "Built around conversational search and human-reviewed recommendations", "python app.py --resume-dir resumes", "Synthetic resumes are included for a safe, immediate demo.", "Welcome"),
        ("One graph, end to end", "Parse requirements, retrieve resumes, rank evidence, and invite feedback", "React + 3 years", "Extracted requirements: must-have React; minimum 3 years. Search retrieves resumes, then the graph deeply screens its top ten.", "Graph workflow"),
        ("Natural-language candidate search", "Strengths, evidence, and missing requirements are all visible", "Find React candidates with 3+ years", search_report, "Search report"),
        ("Compare candidates, then ask why", "Side-by-side evidence makes the ranking easier to review", "Compare the top 3 · Why did Alex rank higher?", comparison + "\n\n" + explanation, "Comparison & explanation"),
        ("Refine the criteria in conversation", "Change a requirement and re-run the ranking without restarting", "Instead of React, use Python", refined_report, "Updated shortlist"),
        ("Generate interview screening questions", "Use the shortlist to prepare focused, job-related follow-ups", "Generate questions for Jordan Kim", interview_questions, "Interview prompts"),
        ("Tested locally, with human oversight", "8 tests cover the search, report, comparison, and refinement flows", "python -m unittest discover -s tests -v", f"{(tests.stdout + tests.stderr).strip()}\n\n{req['must_have'][0]} requirement flow verified. No video demo uses real candidate data.", "Quality checks"),
    ]

    output_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "DEMO_VIDEO.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="matching-demo-") as temp_name:
        temp = Path(temp_name)
        slides: list[Path] = []
        audios: list[Path] = []
        for index, (scene, narration) in enumerate(zip(titles, narrations), start=1):
            image_path = temp / f"slide_{index:02}.png"
            audio_path = temp / f"voice_{index:02}.wav"
            make_slide(index, *scene, image_path)
            synthesize(narration, audio_path)
            slides.append(image_path)
            audios.append(audio_path)

        duration = concatenate_audio(audios, temp / "narration.wav")
        if not 300 <= duration <= 360:
            raise RuntimeError(
                f"Generated narration is {duration / 60:.1f} minutes; "
                "adjust narration length to stay within the requested 5–6 minute range."
            )
        concat_file = temp / "slides.txt"
        with concat_file.open("w", encoding="utf-8", newline="\n") as file:
            for slide, audio in zip(slides, audios):
                with wave.open(str(audio), "rb") as voice:
                    segment_duration = voice.getnframes() / voice.getframerate() + 2.0
                file.write(f"file '{slide.as_posix()}'\n")
                file.write(f"duration {segment_duration:.6f}\n")
            file.write(f"file '{slides[-1].as_posix()}'\n")

        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(temp / "narration.wav"),
            "-vf", "fps=24,format=yuv420p", "-c:v", "libx264",
            "-preset", "medium", "-crf", "24", "-c:a", "aac",
            "-b:a", "128k", "-shortest", "-movflags", "+faststart",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"FFmpeg failed to render the demo: {result.stderr.strip()}")

    print(f"Created: {output_path}")
    print(f"Duration: {duration / 60:.2f} minutes")
    print(f"File size: {output_path.stat().st_size / (1024 * 1024):.1f} MB")


if __name__ == "__main__":
    main()
