using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace RemovalProcess.Client
{
    // --- DTO ---

    public class StockDto
    {
        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("params")]
        public Dictionary<string, object> Params { get; set; } = new Dictionary<string, object>();
    }

    public class OperationDto
    {
        [JsonProperty("op")]
        public string Op { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("selector")]
        public string Selector { get; set; }

        [JsonProperty("workplane")]
        public string Workplane { get; set; }

        [JsonProperty("csys")]
        public Dictionary<string, IList<double>> Csys { get; set; }

        [JsonProperty("params")]
        public Dictionary<string, object> Params { get; set; } = new Dictionary<string, object>();
    }

    public class PipelineRequestDto
    {
        [JsonProperty("units")]
        public string Units { get; set; } = "mm";

        [JsonProperty("origin")]
        public string Origin { get; set; } = "world";

        [JsonProperty("stock")]
        public StockDto Stock { get; set; }

        [JsonProperty("operations")]
        public List<OperationDto> Operations { get; set; } = new List<OperationDto>();

        [JsonProperty("output_mode")]
        public string OutputMode { get; set; } = "stl";

        [JsonProperty("file_template_solid")]
        public string FileTemplateSolid { get; set; } = "case_{step:02d}_{name}_solid.stl";

        [JsonProperty("file_template_removed")]
        public string FileTemplateRemoved { get; set; } = "case_{step:02d}_{name}_removed.stl";

        [JsonProperty("dry_run")]
        public bool DryRun { get; set; } = false;
    }

    public class StepResultDto
    {
        [JsonProperty("step")]
        public int Step { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("op")]
        public string Op { get; set; }

        [JsonProperty("solid")]
        public string Solid { get; set; }

        [JsonProperty("removed")]
        public string Removed { get; set; }
    }

    public class PipelineResponseDto
    {
        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("steps")]
        public List<StepResultDto> Steps { get; set; }
    }

    // --- API クライアント本体 ---

    public class RemovalProcessApiClient : IDisposable
    {
        private readonly HttpClient _httpClient;
        private bool _disposed;

        public RemovalProcessApiClient(string baseAddress)
        {
            if (string.IsNullOrWhiteSpace(baseAddress))
                throw new ArgumentNullException(nameof(baseAddress));

            _httpClient = new HttpClient
            {
                BaseAddress = new Uri(baseAddress, UriKind.Absolute)
            };
        }

        /// <summary>
        /// DTO を使って /pipeline/run を叩く。
        /// </summary>
        public async Task<PipelineResponseDto> PostPipelineAsync(PipelineRequestDto request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));

            var json = JsonConvert.SerializeObject(request);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            using (var response = await _httpClient.PostAsync("/pipeline/run", content).ConfigureAwait(false))
            {
                var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    // FastAPI 側の HTTPException(detail=...) をそのまま文字列で表示
                    throw new InvalidOperationException(
                        $"API error: {(int)response.StatusCode} {response.ReasonPhrase}\n{body}");
                }

                var result = JsonConvert.DeserializeObject<PipelineResponseDto>(body);
                return result;
            }
        }

        /// <summary>
        /// 既存の JSON ファイル（case1_milling.json など）を「生」で投げるパターン。
        /// DTO 作成が面倒なとき用。
        /// </summary>
        public async Task<string> PostRawJsonAsync(string rawJson)
        {
            if (rawJson == null) throw new ArgumentNullException(nameof(rawJson));

            var content = new StringContent(rawJson, Encoding.UTF8, "application/json");
            using (var response = await _httpClient.PostAsync("/pipeline/run", content).ConfigureAwait(false))
            {
                var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    throw new InvalidOperationException(
                        $"API error: {(int)response.StatusCode} {response.ReasonPhrase}\n{body}");
                }

                return body;
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _httpClient.Dispose();
            _disposed = true;
        }
    }
}
