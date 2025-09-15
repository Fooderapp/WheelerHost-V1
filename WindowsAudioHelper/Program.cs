using System;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using NAudio.Wave;

// Windows Audio Helper: captures default output via WASAPI loopback and prints JSON feature lines to stdout.
// Features: bodyL, bodyR, impact, device

class AudioFeatures
{
    public double bodyL { get; set; }
    public double bodyR { get; set; }
    public double impact { get; set; }
    public double engine { get; set; }
    public string device { get; set; } = "";
}

class Program
{
    static void Main(string[] args)
    {
        try
        {
            // Use default output device loopback for maximum compatibility
            using var capture = new WasapiLoopbackCapture();
            int sr = capture.WaveFormat.SampleRate;
            int ch = capture.WaveFormat.Channels;
            string devName = "Default Output";

            Console.WriteLine(JsonSerializer.Serialize(new { status = "started", device = devName, sr, ch }));
            Console.Out.Flush();

            // States for simple DSP
            double emaFast = 0.0, emaSlow = 0.0, roadEnv = 0.0, engEnv = 0.0, prevSlow = 0.0, impactEnv = 0.0;
            DateTime lastFlush = DateTime.UtcNow;

            // Attack/decay constants (per-sample alphas approximate)
            double atkFast = 0.2, decFast = 0.2; // fast abs envelope
            double atkSlow = 0.02, decSlow = 0.02; // slow abs envelope
            double atkRoad = 0.12, decRoad = 0.08; // road env
            double atkEng = 0.04, decEng = 0.12;   // engine env
            double atkImp = 0.25, decImp = 0.10;   // impact envelope

            capture.DataAvailable += (s, e) =>
            {
                int bytes = e.BytesRecorded;
                int stride = sizeof(float) * ch;
                if (bytes <= 0 || bytes % stride != 0) return;
                for (int i = 0; i < bytes; i += stride)
                {
                    // downmix
                    float acc = 0f;
                    for (int c = 0; c < ch; c++)
                    {
                        acc += BitConverter.ToSingle(e.Buffer, i + c * sizeof(float));
                    }
                    float mono = acc / Math.Max(1, ch);
                    double a = Math.Abs(mono);

                    // fast & slow envelopes of |x|
                    emaFast += (a >= emaFast ? atkFast : decFast) * (a - emaFast);
                    emaSlow += (a >= emaSlow ? atkSlow : decSlow) * (a - emaSlow);

                    // road approx: high freq energy via difference
                    double hf = Math.Max(0.0, emaFast - emaSlow);
                    roadEnv += ((hf >= roadEnv) ? atkRoad : decRoad) * (hf - roadEnv);

                    // engine approx: slow energy
                    engEnv += ((emaSlow >= engEnv) ? atkEng : decEng) * (emaSlow - engEnv);

                    // impact: positive derivative on slow env with short decay
                    double dSlow = Math.Max(0.0, emaSlow - prevSlow);
                    impactEnv += ((dSlow >= impactEnv) ? atkImp : decImp) * (dSlow - impactEnv);
                    prevSlow = emaSlow;
                }

                // Throttle print rate ~60 Hz
                if ((DateTime.UtcNow - lastFlush).TotalMilliseconds >= 16.0)
                {
                    lastFlush = DateTime.UtcNow;
                    // Normalize rough ranges
                    double road = Clamp01(roadEnv / 0.02);
                    double eng = Clamp01(engEnv / 0.015);
                    double imp = Clamp01(impactEnv / 0.01);

                    double bodyR = Math.Max(road, 0.5 * eng);
                    double bodyL = Math.Max(0.8 * road, 0.3 * eng);

                    var obj = new AudioFeatures { bodyL = bodyL, bodyR = bodyR, impact = imp, engine = eng, device = devName };
                    Console.WriteLine(JsonSerializer.Serialize(obj));
                    Console.Out.Flush();
                }
            };

            capture.RecordingStopped += (s, e) =>
            {
                Console.WriteLine(JsonSerializer.Serialize(new { status = "stopped" }));
                Console.Out.Flush();
            };

            capture.StartRecording();
            // Keep process alive
            var quit = new ManualResetEvent(false);
            Console.CancelKeyPress += (s, e) => { e.Cancel = true; quit.Set(); };
            quit.WaitOne();
            capture.StopRecording();
        }
        catch (Exception ex)
        {
            var err = new { status = "error", message = ex.Message };
            Console.WriteLine(JsonSerializer.Serialize(err));
        }
    }

    static double Clamp01(double v) => v < 0 ? 0 : (v > 1 ? 1 : v);
}
