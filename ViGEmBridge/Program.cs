// ViGEmBridge/Program.cs
// STDIN/STDOUT JSON bridge (no sockets).
// Control line: {"type":"target","value":"x360"|"ds4"}
// Input lines:  {"lx":-1..1,"ly":-1..1,"rt":0..255,"lt":0..255,"buttons":uint}
// Output lines: {"type":"ffb","rumbleL":0..1,"rumbleR":0..1}

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Nefarius.ViGEm.Client;
using Nefarius.ViGEm.Client.Targets;
using Nefarius.ViGEm.Client.Targets.Xbox360;
using Nefarius.ViGEm.Client.Targets.DualShock4;

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
    static IXbox360Controller? pad360;
    static IDualShock4Controller? padDs4;
    static string target = "x360";

    static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;

        try
        {
            client = new ViGEmClient();
            CreatePad("x360");
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
                // Control messages
                using (var doc = JsonDocument.Parse(line))
                {
                    var root = doc.RootElement;
                    if (root.TryGetProperty("type", out var tProp))
                    {
                        var tVal = tProp.GetString();
                        if (tVal == "target")
                        {
                            var v = root.TryGetProperty("value", out var vProp) ? vProp.GetString() : null;
                            if (!string.IsNullOrEmpty(v)) CreatePad(v!);
                            continue;
                        }
                    }
                }

                var p = JsonSerializer.Deserialize<PacketIn>(line);
                if (p == null) continue;

                short lx = (short)Math.Clamp((int)(p.lx * 32767f), -32767, 32767);
                short ly = (short)Math.Clamp((int)(p.ly * 32767f), -32767, 32767);

                if (target == "ds4" && padDs4 != null)
                {
                    padDs4.SetAxisValue(DualShock4Axis.LeftThumbX, lx);
                    padDs4.SetAxisValue(DualShock4Axis.LeftThumbY, ly);
                    padDs4.SetSliderValue(DualShock4Slider.RightTrigger, p.rt);
                    padDs4.SetSliderValue(DualShock4Slider.LeftTrigger, p.lt);

                    // Map buttons: A->Cross, B->Circle, X->Square, Y->Triangle
                    void SetDs4(uint bit, DualShock4Button btn)
                    {
                        bool on = ((p.buttons >> (int)bit) & 1u) != 0;
                        padDs4.SetButtonState(btn, on);
                    }
                    SetDs4(0, DualShock4Button.Cross);
                    SetDs4(1, DualShock4Button.Circle);
                    SetDs4(2, DualShock4Button.Square);
                    SetDs4(3, DualShock4Button.Triangle);
                    SetDs4(4, DualShock4Button.ShoulderLeft);
                    SetDs4(5, DualShock4Button.ShoulderRight);
                    SetDs4(6, DualShock4Button.Options);
                    SetDs4(7, DualShock4Button.Share);
                    // D-Pad (hat)
                    bool up    = ((p.buttons >> 8) & 1u) != 0;
                    bool down  = ((p.buttons >> 9) & 1u) != 0;
                    bool left  = ((p.buttons >>10) & 1u) != 0;
                    bool right = ((p.buttons >>11) & 1u) != 0;
                    var dpad = DualShock4DPadDirection.None;
                    if (up && !down && !left && !right) dpad = DualShock4DPadDirection.North;
                    else if (up && right) dpad = DualShock4DPadDirection.NorthEast;
                    else if (right && !up && !down) dpad = DualShock4DPadDirection.East;
                    else if (right && down) dpad = DualShock4DPadDirection.SouthEast;
                    else if (down && !left && !right) dpad = DualShock4DPadDirection.South;
                    else if (down && left) dpad = DualShock4DPadDirection.SouthWest;
                    else if (left && !up && !down) dpad = DualShock4DPadDirection.West;
                    else if (left && up) dpad = DualShock4DPadDirection.NorthWest;
                    else dpad = DualShock4DPadDirection.None;
                    padDs4.SetDPadDirection(dpad);

                    padDs4.SubmitReport();
                }
                else if (pad360 != null)
                {
                    pad360.SetAxisValue(Xbox360Axis.LeftThumbX, lx);
                    pad360.SetAxisValue(Xbox360Axis.LeftThumbY, ly);
                    pad360.SetSliderValue(Xbox360Slider.RightTrigger, p.rt);
                    pad360.SetSliderValue(Xbox360Slider.LeftTrigger, p.lt);

                    // Button mask layout (bits):
                    // 0:A 1:B 2:X 3:Y 4:LB 5:RB 6:Start 7:Back 8:Up 9:Down 10:Left 11:Right
                    void Set360(uint bit, Xbox360Button btn)
                    {
                        bool on = ((p.buttons >> (int)bit) & 1u) != 0;
                        pad360.SetButtonState(btn, on);
                    }
                    Set360(0, Xbox360Button.A);
                    Set360(1, Xbox360Button.B);
                    Set360(2, Xbox360Button.X);
                    Set360(3, Xbox360Button.Y);
                    Set360(4, Xbox360Button.LeftShoulder);
                    Set360(5, Xbox360Button.RightShoulder);
                    Set360(6, Xbox360Button.Start);
                    Set360(7, Xbox360Button.Back);
                    Set360(8, Xbox360Button.Up);
                    Set360(9, Xbox360Button.Down);
                    Set360(10, Xbox360Button.Left);
                    Set360(11, Xbox360Button.Right);

                    pad360.SubmitReport();
                }
            }
            catch
            {
                // ignore malformed lines
            }
        }

        try { pad360?.Disconnect(); } catch { }
        try { padDs4?.Disconnect(); } catch { }
        try { client?.Dispose(); } catch { }
        return 0;
    }

    static void OnFeedback360(object? sender, Xbox360FeedbackReceivedEventArgs e)
    {
        float L = Math.Clamp(e.LargeMotor / 255f, 0f, 1f);
        float R = Math.Clamp(e.SmallMotor / 255f, 0f, 1f);
        Console.WriteLine($"{{\"type\":\"ffb\",\"rumbleL\":{L:0.###},\"rumbleR\":{R:0.###}}}");
        Console.Out.Flush();
    }

    static void OnFeedbackDs4(object? sender, DualShock4FeedbackReceivedEventArgs e)
    {
        float L = Math.Clamp(e.LargeMotor / 255f, 0f, 1f);
        float R = Math.Clamp(e.SmallMotor / 255f, 0f, 1f);
        Console.WriteLine($"{{\"type\":\"ffb\",\"rumbleL\":{L:0.###},\"rumbleR\":{R:0.###}}}");
        Console.Out.Flush();
    }

    static void CreatePad(string tgt)
    {
        tgt = (tgt ?? "x360").Trim().ToLowerInvariant();
        if (client == null) return;
        try { pad360?.Disconnect(); } catch { }
        try { padDs4?.Disconnect(); } catch { }
        pad360 = null; padDs4 = null; target = tgt;
        try
        {
            if (target == "ds4")
            {
                padDs4 = client.CreateDualShock4Controller();
                padDs4.FeedbackReceived += OnFeedbackDs4;
                padDs4.Connect();
            }
            else
            {
                pad360 = client.CreateXbox360Controller();
                pad360.FeedbackReceived += OnFeedback360;
                pad360.Connect();
            }
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"ERR CreatePad({tgt}): {e.Message}");
        }
    }
}
