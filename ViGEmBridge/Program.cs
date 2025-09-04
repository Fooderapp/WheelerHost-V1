// ViGEmBridge/Program.cs
// STDIN/STDOUT JSON bridge (no sockets).
// Input lines:  {"lx":-1..1,"ly":-1..1,"rt":0..255,"lt":0..255,"buttons":uint}
// Output lines: {"type":"ffb","rumbleL":0..1,"rumbleR":0..1}

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Nefarius.ViGEm.Client;
using Nefarius.ViGEm.Client.Targets;
using Nefarius.ViGEm.Client.Targets.Xbox360;

class PacketIn
{
    public float lx { get; set; }
    public float ly { get; set; }
    public byte rt { get; set; }
    public byte lt { get; set; }
    public uint buttons { get; set; }
}

class Program
{
    static ViGEmClient? client;
    static IXbox360Controller? pad;

    static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;

        try
        {
            client = new ViGEmClient();
            pad = client.CreateXbox360Controller();
            pad.Connect();
            pad.FeedbackReceived += OnFeedback;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"ERR ViGEm init: {e.Message}");
            return 1;
        }

        // Tell parent we're ready
        Console.WriteLine("{\"type\":\"ready\"}");
        Console.Out.Flush();

        // Read JSON lines from stdin forever
        string? line;
        var stdin = Console.In;
        while ((line = await stdin.ReadLineAsync()) != null)
        {
            if (string.IsNullOrWhiteSpace(line) || line![0] != '{')
                continue;

            try
            {
                var p = JsonSerializer.Deserialize<PacketIn>(line);
                if (p == null || pad == null) continue;

                short lx = (short)Math.Clamp((int)(p.lx * 32767f), -32767, 32767);
                short ly = (short)Math.Clamp((int)(p.ly * 32767f), -32767, 32767);

                pad.SetAxisValue(Xbox360Axis.LeftThumbX, lx);
                pad.SetAxisValue(Xbox360Axis.LeftThumbY, ly);
                pad.SetSliderValue(Xbox360Slider.RightTrigger, p.rt);
                pad.SetSliderValue(Xbox360Slider.LeftTrigger, p.lt);

                // Button mask layout (bits):
                // 0:A 1:B 2:X 3:Y 4:LB 5:RB 6:Start 7:Back 8:Up 9:Down 10:Left 11:Right
                void Set(uint bit, Xbox360Button btn)
                {
                    bool on = ((p.buttons >> (int)bit) & 1u) != 0;
                    pad.SetButtonState(btn, on);
                }
                Set(0, Xbox360Button.A);
                Set(1, Xbox360Button.B);
                Set(2, Xbox360Button.X);
                Set(3, Xbox360Button.Y);
                Set(4, Xbox360Button.LeftShoulder);
                Set(5, Xbox360Button.RightShoulder);
                Set(6, Xbox360Button.Start);
                Set(7, Xbox360Button.Back);
                Set(8, Xbox360Button.Up);
                Set(9, Xbox360Button.Down);
                Set(10, Xbox360Button.Left);
                Set(11, Xbox360Button.Right);

                pad.SubmitReport();
            }
            catch
            {
                // ignore malformed lines
            }
        }

        try { pad?.Disconnect(); } catch { }
        try { client?.Dispose(); } catch { }
        return 0;
    }

    static void OnFeedback(object? sender, Xbox360FeedbackReceivedEventArgs e)
    {
        float L = Math.Clamp(e.LargeMotor / 255f, 0f, 1f);
        float R = Math.Clamp(e.SmallMotor / 255f, 0f, 1f);
        // Write one line JSON to stdout
        Console.WriteLine($"{{\"type\":\"ffb\",\"rumbleL\":{L:0.###},\"rumbleR\":{R:0.###}}}");
        Console.Out.Flush();
    }
}
