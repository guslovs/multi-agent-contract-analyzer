from typing import Literal
from agents import Agent, GuardrailFunctionOutput, InputGuardrailTripwireTriggered, Runner, input_guardrail, trace
import gradio as gr
from dotenv import load_dotenv
from pydantic import BaseModel
from instructions import INSTRUCTIONS

load_dotenv(override=True)

class RiskItem(BaseModel):
    clause: str        
    description: str      
    severity: Literal["Low", "Medium", "High"]
    
class RiskAnalysis(BaseModel):
    risks: list[RiskItem]
    
class Obligation(BaseModel):
    responsible_party: str  
    description: str         
    deadline: str            
    is_payment: bool   
    
class ObligationExtraction(BaseModel):
    obligations: list[Obligation]
    
class GuardrailOutput(BaseModel):
    is_contract: bool
    
class PartyObligations(BaseModel):
    party: str
    obligations: list[str]
    
class FinalReport(BaseModel):
    executive_summary: str
    top_risks: list[RiskItem]          
    obligations_by_party: list[PartyObligations]  
    overall_risk_rating: Literal["Low", "Medium", "High"]
    recommendation: str

guardrail_agent = Agent(
    name="Guardrail Agent",
    model="gpt-4o-mini",
    instructions=INSTRUCTIONS["GUARDRAIL_INSTRUCTIONS"],
    output_type=GuardrailOutput
)

@input_guardrail
async def contract_guardrail(ctx, agent, input):
    result = await Runner.run(guardrail_agent, input, context=ctx.context)
    is_contract = result.final_output.is_contract    
    return GuardrailFunctionOutput(output_info=result.final_output, tripwire_triggered=not is_contract)

risk_identifier_agent = Agent(
    name="Risk Identifier Agent",
    model="gpt-4o-mini",
    instructions=INSTRUCTIONS["RISK_IDENTIFIER_AGENT_INSTRUCTIONS"],
    output_type=RiskAnalysis
)

obligation_extractor_agent = Agent(
    name="Obligation Extractor Agent",
    model="gpt-4o-mini",
    instructions=INSTRUCTIONS["OBLIGATION_EXTRACTOR_AGENT_INSTRUCTIONS"],
    output_type=ObligationExtraction
)

summary_agent = Agent(
    name="Summary Agent",
    model="gpt-4o-mini",
    instructions=INSTRUCTIONS["SUMMARY_AGENT_INSTRUCTIONS"],
    output_type=FinalReport
)

orchestrator_agent = Agent(
    name="Orchestrator Agent",
    model="gpt-4o-mini",
    instructions=INSTRUCTIONS["ORCHESTRATOR_AGENT_INSTRUCTIONS"],
    tools=[
        risk_identifier_agent.as_tool(
            tool_name="identify_risks",
            tool_description="Extract risky clauses from the contract"
        ),
        obligation_extractor_agent.as_tool(
            tool_name="extract_obligations",
            tool_description="Extract obligations, deadlines and payments from the contract"
        ),
        summary_agent.as_tool(
            tool_name="generate_summary",
            tool_description="Generate a final structured FinalReport from all gathered analysis"
        ),
    ],
    input_guardrails=[contract_guardrail],
    output_type=FinalReport
)

async def chat(input):
    with trace("Contract Analizer"):
        result = await Runner.run(orchestrator_agent, input, max_turns=10)
        return result.final_output

async def analyze_contract(contract_text):
    try:
        report = await chat(contract_text)

        risks_text = ""
        for risk in report.top_risks:
            risks_text += f"**[{risk.severity}]** {risk.clause}\n{risk.description}\n\n"

        obligations_text = ""
        for party_ob in report.obligations_by_party:
            obligations_text += f"**{party_ob.party}**\n"
        for ob in party_ob.obligations:
            obligations_text += f"- {ob}\n"
        obligations_text += "\n"

        return (
            report.executive_summary,
            risks_text,
            obligations_text,
            report.overall_risk_rating,
            report.recommendation,
            ""
        )

    except InputGuardrailTripwireTriggered:
        return "", "", "", "", "", "Input does not appear to be a contract. Please paste a valid contract."


with gr.Blocks(title="Contract Analyzer") as ui:
    gr.Markdown("Contract Analyzer")
    gr.Markdown("Paste a construction contract below and get an AI-powered analysis.")

    contract_input = gr.Textbox(
        label="Contract Text",
        placeholder="Paste your contract here...",
        lines=20
    )

    analyze_btn = gr.Button("Analyze Contract", variant="primary")
    error_output = gr.Markdown()

    with gr.Tabs():
        with gr.Tab("Summary"):
            summary_output = gr.Markdown(label="Executive Summary")
            rating_output = gr.Textbox(label="Overall Risk Rating", interactive=False)
            recommendation_output = gr.Markdown(label="Recommendation")

        with gr.Tab("Risks"):
            risks_output = gr.Markdown(label="Top Risks")

        with gr.Tab("Obligations"):
            obligations_output = gr.Markdown(label="Obligations by Party")

    analyze_btn.click(
        fn=analyze_contract,
        inputs=[contract_input],
        outputs=[summary_output, risks_output, obligations_output, rating_output, recommendation_output, error_output]
    )

if __name__ == "__main__":
    ui.launch()
