# stock_workflow.py
import asyncio
from datetime import timedelta
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker

# --- Activities ---
@activity.defn
async def fetch_stock_data(symbol: str) -> dict:
    """Fetch stock data using yfinance"""
    import yfinance as yf
    
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        history = stock.history(period="1d")
        
        return {
            "symbol": symbol,
            "price": info.get("regularMarketPrice", 0),
            "change": info.get("regularMarketChangePercent", 0),
            "volume": info.get("regularMarketVolume", 0),
            "success": True
        }
    except Exception as e:
        return {
            "symbol": symbol,
            "error": str(e),
            "success": False
        }

@activity.defn
async def analyze_sentiment(symbol: str, news_text: str) -> dict:
    """Analyze sentiment"""
    # You can add AI here later
    return {
        "symbol": symbol,
        "sentiment_score": 0.65,
        "sentiment_label": "BULLISH",
        "summary": f"Analysis for {symbol} shows positive sentiment"
    }

# --- Workflow ---
@workflow.defn
class StockAnalysisWorkflow:
    @workflow.run
    async def run(self, symbol: str) -> dict:
        # Fetch stock data
        stock_data = await workflow.execute_activity(
            fetch_stock_data,
            symbol,
            schedule_to_close_timeout=timedelta(seconds=30)
        )
        
        if not stock_data["success"]:
            return stock_data
        
        # Analyze sentiment
        sentiment = await workflow.execute_activity(
            analyze_sentiment,
            symbol,
            f"Recent news about {symbol} shows strong market confidence",
            schedule_to_close_timeout=timedelta(seconds=30)
        )
        
        return {
            "symbol": symbol,
            "stock_data": stock_data,
            "sentiment": sentiment,
            "timestamp": workflow.now().isoformat()
        }

# --- Worker ---
async def run_worker():
    client = await Client.connect("localhost:7233")
    
    worker = Worker(
        client,
        task_queue="stock-task-queue",
        workflows=[StockAnalysisWorkflow],
        activities=[fetch_stock_data, analyze_sentiment],
    )
    
    print("🧑‍💻 Worker started! Listening for tasks on localhost:7233")
    await worker.run()

# --- Client ---
async def start_workflow(symbol: str = "AAPL"):
    client = await Client.connect("localhost:7233")
    
    result = await client.execute_workflow(
        StockAnalysisWorkflow.run,
        symbol,
        id=f"stock-analysis-{symbol}",
        task_queue="stock-task-queue",
        execution_timeout=timedelta(minutes=5),
    )
    
    print(f"✅ Workflow completed for {symbol}:")
    if result.get("stock_data", {}).get("success"):
        print(f"   Price: ${result['stock_data']['price']}")
        print(f"   Change: {result['stock_data']['change']}%")
        print(f"   Sentiment: {result['sentiment']['sentiment_label']}")
        print(f"   Score: {result['sentiment']['sentiment_score']}")
    else:
        print(f"   Error: {result.get('error', 'Unknown error')}")
    
    return result

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        asyncio.run(run_worker())
    else:
        symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
        asyncio.run(start_workflow(symbol))
