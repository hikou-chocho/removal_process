using System;
using System.IO;
using System.Threading.Tasks;
using RemovalProcess.Client;

namespace RemovalProcess.TestClient
{
    internal class Program
    {
        static int Main(string[] args)
        {
            try
            {
                // 同期 Main から async 呼び出し
                RunAsync(args).GetAwaiter().GetResult();
                return 0;
            }
            catch (Exception ex)
            {
                Console.WriteLine("ERROR:");
                Console.WriteLine(ex);
                return 1;
            }
        }

        private static async Task RunAsync(string[] args)
        {
            // API の URL（必要に応じて変更）
            var baseAddress = "http://localhost:8000";

            // presets JSON のパス（リポジトリ構成に合わせて変更）
            // 例: project_root\data\input\case1_milling.json
            var jsonPath = Path.Combine("..", "..", "..", "..", "data", "input", "case1_milling.json");

            if (!File.Exists(jsonPath))
            {
                Console.WriteLine("JSON file not found: " + jsonPath);
                return;
            }

            var rawJson = File.ReadAllText(jsonPath);

            using (var client = new RemovalProcessApiClient(baseAddress))
            {
                Console.WriteLine("POST /pipeline/run ...");
                var responseJson = await client.PostRawJsonAsync(rawJson);

                Console.WriteLine("=== Response JSON ===");
                Console.WriteLine(responseJson);

                // 型付きで扱いたい場合は以下のようにもできる
                // var dto = JsonConvert.DeserializeObject<PipelineResponseDto>(responseJson);
                // Console.WriteLine($"status={dto.Status}, steps={dto.Steps?.Count}");
            }

            Console.WriteLine("Done.");
        }
    }
}
